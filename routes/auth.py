from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Message
from database import db, User, Notification, EmailVerification
import secrets
import re
import os
import json
from datetime import datetime, timedelta
from urllib.parse import urljoin

from mobile_session import signed_session_cookie_pair

from philippine_address_service import (
    get_barangays_for_city,
    get_cities_for_province,
    get_provinces_for_region,
    get_regions_list,
)

auth_bp = Blueprint('auth', __name__)


def _mail_fail_open():
    """Only when MAIL_FAIL_OPEN=true — shows OTP on site if email cannot be sent."""
    from app import app
    return bool(app.config.get('MAIL_FAIL_OPEN'))


def _email_send_failed_message():
    from app import app
    from email_delivery import brevo_api_configured, email_ready, last_send_error

    sender = (app.config.get('MAIL_USERNAME') or '').strip()

    if os.environ.get('RENDER', '').strip() and not email_ready(app):
        return (
            'Email is not configured on Render. Add BREVO_API_KEY starting with xkeysib- '
            '(Brevo → SMTP & API → API Keys), save Environment, then Manual Deploy. '
            'Gmail SMTP does not work on Render.'
        )
    if last_send_error and 'xsmtpsib' in last_send_error.lower():
        return last_send_error
    if not brevo_api_configured(app) and last_send_error and (
        'verify a domain' in last_send_error.lower()
        or 'only send testing emails' in last_send_error.lower()
    ):
        return (
            f'Resend cannot send to this address on the free tier. Sign up at brevo.com (free), '
            f'verify {sender or "your Gmail"} as sender, add BREVO_API_KEY to Render Environment, '
            f'and redeploy — then OTP works for any email.'
        )
    if brevo_api_configured(app) and last_send_error and 'authorised_ips' in last_send_error.lower():
        return (
            'Brevo blocked this server IP. In Brevo go to Security → Authorized IPs and turn off '
            'IP restriction (or allow all), then try again.'
        )
    if brevo_api_configured(app) and last_send_error and 'not verified' in last_send_error.lower():
        return (
            f'Confirm sender {sender} in Brevo: Senders & IP → verify the email Brevo sent you, '
            f'then try again.'
        )
    return 'Could not send email. Please try again later or contact support.'


def _otp_fail_open_message(otp_code, purpose='verify'):
    """User-visible hint when cloud SMTP is blocked (e.g. Render free tier)."""
    if purpose == 'reset':
        label = 'password reset'
    else:
        label = 'account verification'
    return (
        f'Email could not be sent from this server. Use this code for {label}: '
        f'<strong>{otp_code}</strong> (also shown below).'
    )


def _stash_inline_otp(email, otp_code, purpose):
    session['inline_otp'] = otp_code
    session['inline_otp_email'] = email
    session['inline_otp_purpose'] = purpose


def _clear_inline_otp():
    session.pop('inline_otp', None)
    session.pop('inline_otp_email', None)
    session.pop('inline_otp_purpose', None)


def _inline_otp_context(prefilled_email=''):
    otp = session.get('inline_otp')
    email = session.get('inline_otp_email') or prefilled_email
    purpose = session.get('inline_otp_purpose', 'verify')
    if not otp:
        return {}
    return {'inline_otp': otp, 'inline_otp_email': email, 'inline_otp_purpose': purpose}


def _verify_otp_template_kwargs(prefilled_email=''):
    return {'prefilled_email': prefilled_email, **_inline_otp_context(prefilled_email)}


def _verify_reset_otp_template_kwargs(prefilled_email=''):
    return {'prefilled_email': prefilled_email, **_inline_otp_context(prefilled_email)}


def is_api_request():
    accept = request.headers.get('Accept', '')
    return request.is_json or 'application/json' in accept

def validate_contact_number(contact):
    """Validate that contact number contains only digits"""
    return re.match(r'^\d+$', contact) is not None

def validate_password_strength(password):
    """
    Validate password strength
    Returns: (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)"
    
    return True, "Password is strong"

def create_verification_token(user_id, email):
    """Create a new 6-digit OTP verification code"""
    # Delete any existing verification tokens for this user
    EmailVerification.query.filter_by(user_id=user_id, is_used=False).delete()

    # Create new 6-digit OTP code (ensure uniqueness among active tokens)
    token = None
    for _ in range(20):
        candidate = f"{secrets.randbelow(1000000):06d}"
        existing = EmailVerification.query.filter_by(token=candidate, is_used=False).first()
        if not existing:
            token = candidate
            break
    if token is None:
        token = secrets.token_urlsafe(16)

    expires_at = datetime.utcnow() + timedelta(minutes=10)  # OTP expires in 10 minutes
    
    verification = EmailVerification(
        user_id=user_id,
        token=token,
        email=email,
        expires_at=expires_at
    )
    
    db.session.add(verification)
    db.session.flush()
    
    return token

def send_verification_email(email, verification_token):
    """Send registration OTP via Resend API, SMTP, or inline fallback."""
    from app import app
    from email_delivery import otp_email_html, send_html_email

    otp_page_link = urljoin(
        f"{app.config['APP_BASE_URL'].rstrip('/')}/",
        url_for('auth.verify_otp', _external=False).lstrip('/'),
    )
    html = otp_email_html(
        title='Sports and Outdoors',
        heading='Email Verification',
        body='Thank you for registering. Enter this OTP on the verification page:',
        otp_code=verification_token,
        action_link=otp_page_link,
        accent='#28a745',
    )
    return send_html_email(
        app,
        to_email=email,
        subject='Your OTP Code - Sports and Outdoors',
        html=html,
    )


def send_password_reset_otp_email(email, otp_code):
    """Send password-reset OTP via Resend API, SMTP, or inline fallback."""
    from app import app
    from email_delivery import otp_email_html, send_html_email

    otp_page_link = urljoin(
        f"{app.config['APP_BASE_URL'].rstrip('/')}/",
        url_for('auth.verify_reset_otp', _external=False).lstrip('/'),
    )
    html = otp_email_html(
        title='Password Reset',
        heading='Reset Your Password',
        body='Use this OTP code to reset your password:',
        otp_code=otp_code,
        action_link=otp_page_link,
        accent='#ffc107',
    )
    return send_html_email(
        app,
        to_email=email,
        subject='Password Reset OTP - Sports and Outdoors',
        html=html,
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        payload = request.get_json(silent=True) if request.is_json else {}
        email = (payload.get('email') if payload else request.form.get('email', '')).strip().lower()
        password = payload.get('password') if payload else request.form.get('password', '')
        if not email or not password:
            if is_api_request():
                return jsonify({'success': False, 'message': 'Email and password are required.'}), 400
            flash('Email and password are required.', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(email=email).first()
        
        password_ok = user and check_password_hash(user.password_hash, password)
        if not password_ok and user:
            stripped_password = password.strip()
            if stripped_password != password:
                password_ok = check_password_hash(user.password_hash, stripped_password)

        if user and password_ok:
            # Backward compatibility: some legacy buyer accounts may not have is_approved set.
            if user.user_type == 'buyer' and not user.is_approved:
                user.is_approved = True
                db.session.commit()

            # Require email verification before admin approval/login
            if not user.is_verified:
                # Backward compatibility: existing approved accounts created before OTP flow
                # should still be able to login without being blocked by OTP.
                if user.is_approved:
                    user.is_verified = True
                    db.session.commit()
                else:
                    if is_api_request():
                        return jsonify({
                            'success': True,
                            'requires_otp': True,
                            'email': user.email,
                            'role': user.user_type,
                            'approval_status': 'pending' if not user.is_approved else 'approved'
                        }), 200
                    flash('Please verify your email with the OTP code first.', 'warning')
                    return redirect(url_for('auth.verify_otp', email=user.email))

            # Account must also be approved by admin (seller/rider flow)
            if not user.is_approved:
                from database import Notification
                latest_status_notification = Notification.query.filter(
                    Notification.user_id == user.id,
                    Notification.notification_type.in_(['account_approved', 'account_disapproved'])
                ).order_by(Notification.created_at.desc()).first()

                if latest_status_notification and latest_status_notification.notification_type == 'account_disapproved':
                    if is_api_request():
                        return jsonify({'success': False, 'message': 'Account disapproved.', 'approval_status': 'disapproved'}), 403
                    flash('Your account has been disapproved. Please contact support for assistance.', 'error')
                else:
                    if is_api_request():
                        return jsonify({'success': False, 'message': 'Account pending admin approval.', 'approval_status': 'pending'}), 403
                    flash('Your account is pending approval from admin.', 'warning')
                return render_template('auth/login.html')
            
            session['user_id'] = user.id
            session['user_type'] = user.user_type
            session['user_name'] = f"{user.first_name} {user.last_name}"
            if is_api_request():
                return jsonify({
                    'success': True,
                    'token': secrets.token_hex(16),
                    'email': user.email,
                    'role': user.user_type,
                    'approval_status': 'approved',
                }), 200
            
            # Redirect based on user type
            if user.user_type == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.user_type == 'seller':
                return redirect(url_for('seller.dashboard'))
            elif user.user_type == 'rider':
                return redirect(url_for('rider.dashboard'))
            else:
                return redirect(url_for('buyer.dashboard'))
        else:
            if is_api_request():
                return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/api/mobile/login', methods=['POST'])
def mobile_login():
    payload = request.get_json(silent=True) if request.is_json else request.form
    email = ((payload.get('email') if payload else '') or '').strip().lower()
    password = (payload.get('password') if payload else '') or ''

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()
    password_ok = user and check_password_hash(user.password_hash, password)
    if not password_ok and user:
        stripped_password = password.strip()
        if stripped_password != password:
            password_ok = check_password_hash(user.password_hash, stripped_password)

    if not user or not password_ok:
        return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

    # Backward compatibility: some legacy buyer accounts may not have is_approved set.
    if user.user_type == 'buyer' and not user.is_approved:
        user.is_approved = True
        db.session.commit()

    if not user.is_verified:
        # Existing approved accounts created before OTP rollout should still login.
        if user.is_approved:
            user.is_verified = True
            db.session.commit()
        else:
            return jsonify({
                'success': True,
                'requires_otp': True,
                'email': user.email,
                'role': user.user_type,
                'approval_status': 'pending'
            }), 200

    if not user.is_approved:
        latest_status_notification = Notification.query.filter(
            Notification.user_id == user.id,
            Notification.notification_type.in_(['account_approved', 'account_disapproved'])
        ).order_by(Notification.created_at.desc()).first()

        if latest_status_notification and latest_status_notification.notification_type == 'account_disapproved':
            return jsonify({
                'success': False,
                'message': 'Account disapproved.',
                'approval_status': 'disapproved'
            }), 403

        return jsonify({
            'success': False,
            'message': 'Account pending admin approval.',
            'approval_status': 'pending'
        }), 403

    session['user_id'] = user.id
    session['user_type'] = user.user_type
    session['user_name'] = f"{user.first_name} {user.last_name}"

    return jsonify({
        'success': True,
        'token': secrets.token_hex(16),
        'email': user.email,
        'role': user.user_type,
        'approval_status': 'approved',
        'session_cookie': signed_session_cookie_pair(),
    }), 200


@auth_bp.route('/api/addresses/regions', methods=['GET'])
def api_addresses_regions():
    try:
        regions = [
            {'region_code': r['region_code'], 'region_name': r['region_name']}
            for r in get_regions_list()
        ]
        return jsonify({'success': True, 'regions': regions})
    except OSError as e:
        return jsonify({'success': False, 'message': f'Address data unavailable: {e}'}), 500


@auth_bp.route('/api/addresses/provinces', methods=['GET'])
def api_addresses_provinces():
    rc = request.args.get('region_code', '').strip()
    if not rc:
        return jsonify({'success': False, 'message': 'region_code is required.'}), 400
    try:
        return jsonify({'success': True, 'provinces': get_provinces_for_region(rc)})
    except OSError as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/api/addresses/cities', methods=['GET'])
def api_addresses_cities():
    pc = request.args.get('province_code', '').strip()
    if not pc:
        return jsonify({'success': False, 'message': 'province_code is required.'}), 400
    try:
        return jsonify({'success': True, 'cities': get_cities_for_province(pc)})
    except OSError as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/api/addresses/barangays', methods=['GET'])
def api_addresses_barangays():
    cc = request.args.get('city_code', '').strip()
    if not cc:
        return jsonify({'success': False, 'message': 'city_code is required.'}), 400
    try:
        return jsonify({'success': True, 'barangays': get_barangays_for_city(cc)})
    except OSError as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        payload = request.get_json(silent=True) if request.is_json else {}
        def render_register_error(message, field_id=None):
            if is_api_request():
                return jsonify({'success': False, 'message': message, 'field': field_id}), 400
            flash(message, 'error')
            flat_form_data = request.form.to_dict()
            multi_form_data = request.form.to_dict(flat=False)
            return render_template(
                'auth/register.html',
                form_data=flat_form_data,
                form_data_multi=multi_form_data,
                error_field=field_id,
                error_message=message
            )

        email = (payload.get('email') if payload else request.form.get('email', '')).strip().lower()
        password = payload.get('password') if payload else request.form.get('password', '')
        confirm_password = payload.get('confirm_password') if payload else request.form.get('confirm_password', '')
        first_name = payload.get('first_name') if payload else request.form.get('first_name', '')
        last_name = payload.get('last_name') if payload else request.form.get('last_name', '')
        contact_number = payload.get('contact_number') if payload else request.form.get('contact_number', '')
        address_region = payload.get('address_region') if payload else request.form.get('address_region', '')
        address_province = payload.get('address_province') if payload else request.form.get('address_province', '')
        address_city = payload.get('address_city') if payload else request.form.get('address_city', '')
        address_barangay = payload.get('address_barangay') if payload else request.form.get('address_barangay', '')
        address_street = payload.get('address_street', '') if payload else request.form.get('address_street', '')
        user_type = payload.get('user_type') if payload else request.form.get('user_type', 'buyer')
        terms_accepted = payload.get('terms_accepted') if payload else request.form.get('terms_accepted')
        
        # Validation
        if not terms_accepted:
            return render_register_error('Please accept the terms and conditions.', 'terms_accepted')
        
        if password != confirm_password:
            return render_register_error('Passwords do not match.', 'confirm_password')
        
        # Validate password strength
        is_valid_password, password_error = validate_password_strength(password)
        if not is_valid_password:
            return render_register_error(password_error, 'password')
        
        if not validate_contact_number(contact_number):
            return render_register_error('Contact number should contain only numbers.', 'contact_number')

        address_region = (address_region or '').strip()
        address_province = (address_province or '').strip()
        address_city = (address_city or '').strip()
        address_barangay = (address_barangay or '').strip()
        if not address_region or not address_province or not address_city or not address_barangay:
            return render_register_error(
                'Please complete your address (region, province, city/municipality, and barangay).',
                'address_region',
            )

        if User.query.filter_by(email=email).first():
            return render_register_error('Email already registered.', 'email')
        
        # Handle seller-specific fields
        product_categories = None
        business_permit = None
        
        if user_type == 'seller':
            product_categories = payload.get('product_categories') if payload else request.form.getlist('product_categories')
            if isinstance(product_categories, list) and len(product_categories) == 1:
                one = str(product_categories[0]).strip()
                if one.startswith('['):
                    try:
                        parsed = json.loads(one)
                        if isinstance(parsed, list):
                            product_categories = [str(v).strip() for v in parsed if str(v).strip()]
                    except Exception:
                        pass
            if isinstance(product_categories, str):
                raw = product_categories.strip()
                if raw.startswith('['):
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, list):
                            product_categories = [str(v).strip() for v in parsed if str(v).strip()]
                        else:
                            product_categories = [raw]
                    except Exception:
                        product_categories = [raw]
                else:
                    product_categories = [raw]
            if not product_categories:
                return render_register_error('Please select at least one product category.', 'cat_fitness_equipment')
            
        # Handle file upload for business permit
        if user_type == 'seller':
            if 'business_permit' in request.files:
                file = request.files['business_permit']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    os.makedirs(os.path.join('static/uploads/documents'), exist_ok=True)
                    file.save(os.path.join('static/uploads/documents', filename))
                    business_permit = f"documents/{filename}"
                else:
                    return render_register_error('Please upload your business permit.', 'business_permit')
            elif payload and payload.get('business_permit'):
                business_permit = payload.get('business_permit')
            else:
                return render_register_error('Please upload your business permit.', 'business_permit')
        
        # Handle rider-specific fields
        drivers_license = None
        vehicle_type = None
        vehicle_plate = None
        
        if user_type == 'rider':
            vehicle_type = payload.get('vehicle_type') if payload else request.form.get('vehicle_type')
            vehicle_plate = payload.get('vehicle_plate', '') if payload else request.form.get('vehicle_plate', '')
            
            if not vehicle_type:
                return render_register_error('Please select your vehicle type.', 'vehicle_type')
            
            # Driver's license: multipart file works for web and mobile API (mobile sends multipart + Accept: JSON).
            if 'drivers_license' in request.files:
                file = request.files['drivers_license']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    os.makedirs(os.path.join('static/uploads/documents'), exist_ok=True)
                    file.save(os.path.join('static/uploads/documents', filename))
                    drivers_license = f"documents/{filename}"
                else:
                    return render_register_error('Please upload your driver\'s license.', 'drivers_license')
            elif payload and payload.get('drivers_license'):
                drivers_license = payload.get('drivers_license')
            else:
                return render_register_error('Please upload your driver\'s license.', 'drivers_license')
        
        # Create user (email verification required)
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            contact_number=contact_number,
            address_region=address_region,
            address_province=address_province,
            address_city=address_city,
            address_barangay=address_barangay,
            address_street=address_street,
            user_type=user_type,
            product_categories=json.dumps(product_categories) if product_categories else None,
            business_permit=business_permit,
            drivers_license=drivers_license,
            vehicle_type=vehicle_type,
            vehicle_plate=vehicle_plate,
            is_verified=False,
            is_approved=(user_type == 'buyer')
        )
        
        db.session.add(user)
        db.session.flush()  # Get user ID

        try:
            # Create and send email verification token
            verification_token = create_verification_token(user.id, email)
            email_sent = send_verification_email(email, verification_token)
            if not email_sent and not _mail_fail_open():
                db.session.rollback()
                return render_register_error(
                    _email_send_failed_message(),
                    'email',
                )

            # Notify admin about new registration
            admin_users = User.query.filter_by(user_type='admin').all()
            for admin in admin_users:
                notification = Notification(
                    user_id=admin.id,
                    title='New User Registration',
                    message=f'New {user_type} registration from {first_name} {last_name} ({email})',
                    notification_type='registration',
                )
                db.session.add(notification)

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            from app import app
            app.logger.exception('Registration failed: %s', exc)
            if is_api_request():
                return jsonify({'success': False, 'message': 'Registration failed. Please try again.'}), 500
            return render_register_error('Registration failed due to a server error. Please try again.', 'email')

        if is_api_request():
            body = {
                'success': True,
                'message': 'Registration successful. Verify OTP to activate account.',
                'email': email,
                'role': user_type,
                'approval_status': 'approved' if user_type == 'buyer' else 'pending',
            }
            if not email_sent and _mail_fail_open():
                body['otp_code'] = verification_token
                body['otp_delivery'] = 'inline'
                body['message'] += ' OTP included in response (email not sent from server).'
            return jsonify(body), 201

        if not email_sent and _mail_fail_open():
            _stash_inline_otp(email, verification_token, 'verify')
            flash(_otp_fail_open_message(verification_token, 'verify'), 'warning')
        elif user_type == 'buyer':
            flash('Registration successful! Enter the 6-digit OTP sent to your email to activate your account.', 'success')
        else:
            flash('Registration successful! Enter your email OTP first, then wait for admin approval.', 'success')
        return redirect(url_for('auth.verify_otp', email=email))
    
    return render_template('auth/register.html', form_data={}, form_data_multi={}, error_field='', error_message='')

@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    # Find the verification token
    verification = EmailVerification.query.filter_by(token=token, is_used=False).first()
    
    if not verification:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('auth.login'))
    
    # Check if token is expired
    if datetime.utcnow() > verification.expires_at:
        flash('Verification link has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.resend_verification'))
    
    # Get the user
    user = User.query.get(verification.user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('auth.login'))
    
    # Mark user as verified and token as used
    user.is_verified = True
    verification.is_used = True
    db.session.commit()
    
    flash('Email verified successfully! You can now log in.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if request.method == 'POST':
        payload = request.get_json(silent=True) if request.is_json else {}
        email = (payload.get('email') if payload else request.form.get('email', '')).strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            if is_api_request():
                return jsonify({'success': False, 'message': 'Email address not found.'}), 404
            flash('Email address not found.', 'error')
            return render_template('auth/resend_verification.html')
        
        if user.is_verified:
            if is_api_request():
                return jsonify({'success': False, 'message': 'Email is already verified.'}), 400
            flash('Email is already verified. You can log in.', 'info')
            return redirect(url_for('auth.login'))
        
        # Create new verification token
        verification_token = create_verification_token(user.id, email)

        # Send verification email
        if send_verification_email(email, verification_token):
            db.session.commit()
            if is_api_request():
                return jsonify({'success': True, 'message': 'OTP resent successfully.'}), 200
            flash('A new OTP code was sent. Please check your inbox and spam folder.', 'success')
            return redirect(url_for('auth.verify_otp', email=email))

        if _mail_fail_open():
            db.session.commit()
            if is_api_request():
                return jsonify({
                    'success': True,
                    'message': 'OTP not emailed; use inline code.',
                    'otp_code': verification_token,
                    'otp_delivery': 'inline',
                }), 200
            _stash_inline_otp(email, verification_token, 'verify')
            flash(_otp_fail_open_message(verification_token, 'verify'), 'warning')
            return redirect(url_for('auth.verify_otp', email=email))

        db.session.rollback()
        if is_api_request():
            return jsonify({'success': False, 'message': 'Failed to send OTP email.'}), 500
        flash(_email_send_failed_message(), 'error')
        return render_template('auth/resend_verification.html')
    
    return render_template('auth/resend_verification.html')

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    prefilled_email = request.args.get('email', '')

    if request.method == 'POST':
        payload = request.get_json(silent=True) if request.is_json else {}
        email = (payload.get('email') if payload else request.form.get('email', '')).strip().lower()
        otp_code = (payload.get('otp_code') if payload else request.form.get('otp_code', '')).strip()

        if not email or not otp_code:
            if is_api_request():
                return jsonify({'success': False, 'message': 'Email and OTP code are required.'}), 400
            flash('Please provide your email and OTP code.', 'error')
            return render_template('auth/verify_otp.html', **_verify_otp_template_kwargs(email))

        verification = EmailVerification.query.filter_by(
            email=email,
            token=otp_code,
            is_used=False
        ).order_by(EmailVerification.created_at.desc()).first()

        if not verification:
            if is_api_request():
                return jsonify({'success': False, 'message': 'Invalid OTP code.'}), 400
            flash('Invalid OTP code. Please check and try again.', 'error')
            return render_template('auth/verify_otp.html', **_verify_otp_template_kwargs(email))

        if datetime.utcnow() > verification.expires_at:
            if is_api_request():
                return jsonify({'success': False, 'message': 'OTP code has expired.'}), 400
            flash('OTP code has expired. Please request a new code.', 'error')
            return redirect(url_for('auth.resend_verification'))

        user = User.query.get(verification.user_id)
        if not user:
            if is_api_request():
                return jsonify({'success': False, 'message': 'User not found.'}), 404
            flash('User not found.', 'error')
            return redirect(url_for('auth.login'))

        user.is_verified = True
        verification.is_used = True
        db.session.commit()
        _clear_inline_otp()
        if is_api_request():
            return jsonify({
                'success': True,
                'message': 'OTP verified successfully.',
                'token': secrets.token_hex(16),
                'email': user.email,
                'role': user.user_type,
                'approval_status': 'approved' if user.is_approved else 'pending',
            }), 200

        if user.is_approved:
            flash('Email verified successfully! You can now log in.', 'success')
        else:
            flash('Email verified successfully! Your account is pending admin approval.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/verify_otp.html', **_verify_otp_template_kwargs(prefilled_email))

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.home'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            reset_otp = create_verification_token(user.id, email)
            if send_password_reset_otp_email(email, reset_otp):
                db.session.commit()
                flash('Password reset OTP sent! Please check your inbox and spam folder.', 'success')
                return redirect(url_for('auth.verify_reset_otp', email=email))
            db.session.rollback()
            if _mail_fail_open():
                reset_otp = create_verification_token(user.id, email)
                db.session.commit()
                _stash_inline_otp(email, reset_otp, 'reset')
                flash(_otp_fail_open_message(reset_otp, 'reset'), 'warning')
                return redirect(url_for('auth.verify_reset_otp', email=email))
            flash(_email_send_failed_message(), 'error')
        else:
            flash('Email address not found.', 'error')
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/api/forgot-password', methods=['POST'])
def forgot_password_api():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    if not email:
        return jsonify({'success': False, 'message': 'Email is required.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'message': 'Email address not found.'}), 404

    reset_otp = create_verification_token(user.id, email)
    if send_password_reset_otp_email(email, reset_otp):
        db.session.commit()
        return jsonify({'success': True, 'message': 'Password reset OTP sent.'}), 200
    db.session.rollback()
    if _mail_fail_open():
        reset_otp = create_verification_token(user.id, email)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'OTP not emailed; use inline code.',
            'otp_code': reset_otp,
            'otp_delivery': 'inline',
        }), 200
    return jsonify({'success': False, 'message': _email_send_failed_message()}), 500

@auth_bp.route('/verify-reset-otp', methods=['GET', 'POST'])
def verify_reset_otp():
    prefilled_email = request.args.get('email', '')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        otp_code = request.form.get('otp_code', '').strip()

        if not email or not otp_code:
            flash('Please provide your email and OTP code.', 'error')
            return render_template('auth/verify_reset_otp.html', **_verify_reset_otp_template_kwargs(email))

        verification = EmailVerification.query.filter_by(
            email=email,
            token=otp_code,
            is_used=False
        ).order_by(EmailVerification.created_at.desc()).first()

        if not verification:
            flash('Invalid OTP code. Please check and try again.', 'error')
            return render_template('auth/verify_reset_otp.html', **_verify_reset_otp_template_kwargs(email))

        if datetime.utcnow() > verification.expires_at:
            flash('OTP code has expired. Please request a new one.', 'error')
            return redirect(url_for('auth.forgot_password'))

        user = User.query.get(verification.user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('auth.forgot_password'))

        session['password_reset_user_id'] = user.id
        session['password_reset_verification_id'] = verification.id
        return redirect(url_for('auth.reset_password_otp'))

    return render_template('auth/verify_reset_otp.html', **_verify_reset_otp_template_kwargs(prefilled_email))


@auth_bp.route('/api/verify-reset-otp', methods=['POST'])
def verify_reset_otp_api():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    otp_code = (payload.get('otp_code') or '').strip()

    if not email or not otp_code:
        return jsonify({'success': False, 'message': 'Email and OTP code are required.'}), 400

    verification = EmailVerification.query.filter_by(
        email=email,
        token=otp_code,
        is_used=False
    ).order_by(EmailVerification.created_at.desc()).first()

    if not verification:
        return jsonify({'success': False, 'message': 'Invalid OTP code.'}), 400

    if datetime.utcnow() > verification.expires_at:
        return jsonify({'success': False, 'message': 'OTP code has expired.'}), 400

    user = User.query.get(verification.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    return jsonify({'success': True, 'message': 'OTP verified successfully.'}), 200

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password_otp():
    user_id = session.get('password_reset_user_id')
    verification_id = session.get('password_reset_verification_id')
    if not user_id or not verification_id:
        flash('Please verify your reset OTP first.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.get(user_id)
    verification = EmailVerification.query.get(verification_id)
    if not user or not verification or verification.is_used or datetime.utcnow() > verification.expires_at:
        session.pop('password_reset_user_id', None)
        session.pop('password_reset_verification_id', None)
        flash('Reset session expired. Please request a new OTP.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html')
        
        is_valid_password, password_error = validate_password_strength(password)
        if not is_valid_password:
            flash(password_error, 'error')
            return render_template('auth/reset_password.html')
        
        user.password_hash = generate_password_hash(password)
        verification.is_used = True
        db.session.commit()

        session.pop('password_reset_user_id', None)
        session.pop('password_reset_verification_id', None)
        flash('Password reset successfully! You can now log in with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html')


@auth_bp.route('/api/reset-password', methods=['POST'])
def reset_password_api():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    otp_code = (payload.get('otp_code') or '').strip()
    password = payload.get('password') or ''
    confirm_password = payload.get('confirm_password') or ''

    if not email or not otp_code or not password or not confirm_password:
        return jsonify({'success': False, 'message': 'Email, OTP, and passwords are required.'}), 400

    if password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match.'}), 400

    is_valid_password, password_error = validate_password_strength(password)
    if not is_valid_password:
        return jsonify({'success': False, 'message': password_error}), 400

    verification = EmailVerification.query.filter_by(
        email=email,
        token=otp_code,
        is_used=False
    ).order_by(EmailVerification.created_at.desc()).first()

    if not verification:
        return jsonify({'success': False, 'message': 'Invalid OTP code.'}), 400

    if datetime.utcnow() > verification.expires_at:
        return jsonify({'success': False, 'message': 'OTP code has expired.'}), 400

    user = User.query.get(verification.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    user.password_hash = generate_password_hash(password)
    verification.is_used = True
    db.session.commit()

    return jsonify({'success': True, 'message': 'Password reset successfully.'}), 200

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Find the reset token in database
    verification = EmailVerification.query.filter_by(token=token, is_used=False).first()
    
    if not verification:
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    # Check if token is expired
    if datetime.utcnow() > verification.expires_at:
        flash('Reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    # Get the user
    user = User.query.get(verification.user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)
        
        # Validate password strength
        is_valid_password, password_error = validate_password_strength(password)
        if not is_valid_password:
            flash(password_error, 'error')
            return render_template('auth/reset_password.html', token=token)
        
        # Update password and mark token as used
        user.password_hash = generate_password_hash(password)
        verification.is_used = True
        db.session.commit()
        
        flash('Password reset successfully! You can now log in with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)
