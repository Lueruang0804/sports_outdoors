from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_mail import Message
from database import (
    db,
    User,
    Product,
    Order,
    OrderItem,
    Notification,
    Commission,
    Advertisement,
    ChatRoom,
    ChatMessage,
    EmailVerification,
    Delivery,
    filter_orders_by_tab,
    order_pickup_shop_labels,
)
from routes.buyer import (
    _order_timeline_entries,
    _delivery_status_label,
    _proof_of_delivery_dict,
)
from datetime import datetime, timedelta
from sqlalchemy import func, extract
import os
import json
import io
import re
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from timezone_utils import format_ph_datetime, get_ph_time

admin_bp = Blueprint('admin', __name__)


def _get_user_approval_state(user):
    """Resolve user approval state without schema changes."""
    if user.is_approved:
        return 'approved'

    latest_status_notification = Notification.query.filter(
        Notification.user_id == user.id,
        Notification.notification_type.in_(['account_approved', 'account_disapproved'])
    ).order_by(Notification.created_at.desc()).first()

    if latest_status_notification and latest_status_notification.notification_type == 'account_disapproved':
        return 'disapproved'
    return 'pending'


def _send_account_approved_email(user):
    """Send account approval email for seller/rider accounts."""
    if user.user_type not in ['seller', 'rider']:
        return True

    from app import app, mail

    if app.config['MAIL_USERNAME'] == 'your-email@gmail.com' or app.config['MAIL_PASSWORD'] == 'your-app-password':
        print(f"⚠️  EMAIL NOT CONFIGURED: Approval email skipped for {user.email}")
        return False

    role_label = 'Seller' if user.user_type == 'seller' else 'Rider'

    try:
        msg = Message(
            f'{role_label} Account Approved - Sports and Outdoors Ecommerce',
            sender=app.config['MAIL_USERNAME'],
            recipients=[user.email]
        )
        msg.html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                <h2>{role_label} Account Approved</h2>
            </div>
            <div style="background-color: #f8f9fa; padding: 24px; border-radius: 0 0 10px 10px;">
                <p>Hello {user.first_name},</p>
                <p>Your {role_label.lower()} account has been approved by admin.</p>
                <p>You can now log in and access your full dashboard features.</p>
                <p style="margin-top: 24px;">Thank you,<br>Sports and Outdoors Ecommerce Team</p>
            </div>
        </body>
        </html>
        """
        mail.send(msg)
        print(f"SUCCESS: Account approval email sent to {user.email}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to send approval email to {user.email}: {e}")
        return False


def _send_account_disapproved_email(user):
    """Send account disapproval email for seller/rider accounts."""
    if user.user_type not in ['seller', 'rider']:
        return True

    from app import app, mail

    if app.config['MAIL_USERNAME'] == 'your-email@gmail.com' or app.config['MAIL_PASSWORD'] == 'your-app-password':
        print(f"⚠️  EMAIL NOT CONFIGURED: Disapproval email skipped for {user.email}")
        return False

    role_label = 'Seller' if user.user_type == 'seller' else 'Rider'

    try:
        msg = Message(
            f'{role_label} Account Disapproved - Sports and Outdoors Ecommerce',
            sender=app.config['MAIL_USERNAME'],
            recipients=[user.email]
        )
        msg.html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                <h2>{role_label} Account Disapproved</h2>
            </div>
            <div style="background-color: #f8f9fa; padding: 24px; border-radius: 0 0 10px 10px;">
                <p>Hello {user.first_name},</p>
                <p>Your {role_label.lower()} account has been disapproved by admin.</p>
                <p>Please contact support for further assistance.</p>
                <p style="margin-top: 24px;">Thank you,<br>Sports and Outdoors Ecommerce Team</p>
            </div>
        </body>
        </html>
        """
        mail.send(msg)
        print(f"SUCCESS: Account disapproval email sent to {user.email}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to send disapproval email to {user.email}: {e}")
        return False


def _get_period_range(period):
    now = datetime.now()
    if period == 'day':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period == 'week':
        start = now - timedelta(days=6)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now + timedelta(days=1)
    elif period == 'year':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
    else:  # month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def _get_admin_analytics_data(period):
    start_date, end_date = _get_period_range(period)

    sales_rows = db.session.query(
        func.date(Order.created_at).label('date'),
        func.coalesce(func.sum(Order.total_amount), 0).label('total')
    ).filter(
        Order.status == 'delivered',
        Order.created_at >= start_date,
        Order.created_at < end_date
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()

    commission_rows = db.session.query(
        func.date(Commission.created_at).label('date'),
        func.coalesce(func.sum(Commission.platform_commission), 0).label('commission')
    ).filter(
        Commission.created_at >= start_date,
        Commission.created_at < end_date
    ).group_by(func.date(Commission.created_at)).order_by(func.date(Commission.created_at)).all()

    sales_data = [{"date": str(r.date), "total": float(r.total or 0)} for r in sales_rows]
    commission_data = [{"date": str(r.date), "commission": float(r.commission or 0)} for r in commission_rows]
    total_sales_period = round(sum(item["total"] for item in sales_data), 2)
    total_commission_period = round(sum(item["commission"] for item in commission_data), 2)

    return {
        "period": period,
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "sales_data": sales_data,
        "commission_data": commission_data,
        "total_sales_period": total_sales_period,
        "total_commission_period": total_commission_period,
    }

def update_user_activity():
    """Update user's last active timestamp if needed"""
    if 'user_id' in session:
        try:
            user = User.query.get(session['user_id'])
            if user:
                # Only update if it's been more than 5 minutes since last update
                time_diff = (datetime.utcnow() - user.last_active).total_seconds()
                if time_diff > 300:  # Update only every 5 minutes
                    user.last_active = datetime.utcnow()
                    db.session.commit()
        except Exception as e:
            # Don't let database errors crash the app
            pass

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'admin':
            flash('Please login as an admin to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'

    # Get overall statistics
    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_sales = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status == 'delivered'
    ).scalar() or 0
    
    # Get pending approvals
    pending_approvals = User.query.filter_by(is_approved=False, is_verified=True).count()
    
    # Get recent registrations
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    analytics = _get_admin_analytics_data(period)
    
    # Get unread notifications
    unread_notifications = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_products=total_products,
                         total_orders=total_orders,
                         total_sales=total_sales,
                         pending_approvals=pending_approvals,
                         recent_users=recent_users,
                         sales_data=analytics['sales_data'],
                         commission_data=analytics['commission_data'],
                         total_sales_period=analytics['total_sales_period'],
                         total_commission_period=analytics['total_commission_period'],
                         period=period,
                         unread_notifications=unread_notifications)


@admin_bp.route('/dashboard/analytics-data')
@login_required
def dashboard_analytics_data():
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'
    return jsonify(_get_admin_analytics_data(period))


@admin_bp.route('/dashboard/report-pdf')
@login_required
def dashboard_report_pdf():
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'

    analytics = _get_admin_analytics_data(period)

    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_sales = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status == 'delivered'
    ).scalar() or 0

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Admin Analytics Report")
    y -= 24
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Period: {period.title()} ({analytics['start_date']} to {analytics['end_date']})")
    y -= 16
    pdf.drawString(40, y, f"Generated: {format_ph_datetime(get_ph_time(), '%Y-%m-%d %H:%M:%S')}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "System Totals")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, f"Total Users: {total_users}")
    y -= 14
    pdf.drawString(50, y, f"Total Products: {total_products}")
    y -= 14
    pdf.drawString(50, y, f"Total Orders: {total_orders}")
    y -= 14
    pdf.drawString(50, y, f"Lifetime Delivered Sales: PHP {float(total_sales):.2f}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "Selected Period Totals")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, f"Period Sales: PHP {analytics['total_sales_period']:.2f}")
    y -= 14
    pdf.drawString(50, y, f"Period Commission: PHP {analytics['total_commission_period']:.2f}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Daily Sales")
    y -= 18
    pdf.setFont("Helvetica", 10)
    if analytics['sales_data']:
        for row in analytics['sales_data']:
            if y < 60:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y, f"{row['date']}: PHP {row['total']:.2f}")
            y -= 14
    else:
        pdf.drawString(50, y, "No sales data for selected period.")
        y -= 14

    y -= 16
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Daily Commission")
    y -= 18
    pdf.setFont("Helvetica", 10)
    if analytics['commission_data']:
        for row in analytics['commission_data']:
            if y < 60:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y, f"{row['date']}: PHP {row['commission']:.2f}")
            y -= 14
    else:
        pdf.drawString(50, y, "No commission data for selected period.")

    pdf.save()
    buffer.seek(0)
    filename = f"admin_analytics_report_{period}_{get_ph_time().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@admin_bp.route('/users')
@login_required
def users():
    user_type = request.args.get('type', 'all')
    search = request.args.get('search', '')
    
    query = User.query
    
    if user_type != 'all':
        query = query.filter(User.user_type == user_type)
    
    if search:
        query = query.filter(
            (User.first_name.contains(search)) |
            (User.last_name.contains(search)) |
            (User.email.contains(search))
        )
    
    users = query.order_by(User.created_at.desc()).all()
    user_status_map = {user.id: _get_user_approval_state(user) for user in users}

    return render_template(
        'admin/users.html',
        users=users,
        user_status_map=user_status_map,
        current_type=user_type,
        current_search=search
    )

@admin_bp.route('/users/<int:user_id>')
@login_required
def user_details(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        # Get user's products if they're a seller
        products = []
        if user.user_type == 'seller':
            products = Product.query.filter_by(seller_id=user.id).all()
        
        # Get user's orders if they're a buyer
        orders = []
        if user.user_type == 'buyer':
            orders = Order.query.filter_by(buyer_id=user.id).order_by(Order.created_at.desc()).limit(10).all()
        
        # Get user's deliveries if they're a rider
        deliveries = []
        if user.user_type == 'rider':
            deliveries = Delivery.query.filter_by(rider_id=user.id).order_by(Delivery.created_at.desc()).limit(10).all()
        
        # Parse product categories if they exist
        categories = []
        if user.product_categories:
            try:
                categories = json.loads(user.product_categories)
            except (json.JSONDecodeError, TypeError):
                categories = []
        
        return render_template('admin/user_details.html', 
                             user=user, 
                             products=products, 
                             orders=orders, 
                             deliveries=deliveries,
                             categories=categories)
    except Exception as e:
        flash(f'Error loading user details: {str(e)}', 'error')
        return redirect(url_for('admin.users'))

@admin_bp.route('/users/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_approved:
        flash('User is already approved.', 'info')
    else:
        user.is_approved = True
        db.session.commit()
        
        # Notify user
        notification = Notification(
            user_id=user.id,
            title='Account Approved',
            message='Your account has been approved! You can now access all features.',
            notification_type='account_approved'
        )
        db.session.add(notification)
        db.session.commit()

        # Email notify seller/rider approval (non-blocking).
        email_sent = _send_account_approved_email(user)
        if user.user_type in ['seller', 'rider'] and not email_sent:
            flash('User approved, but approval email could not be sent.', 'warning')
        
        flash(f'User {user.first_name} {user.last_name} has been approved.', 'success')
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/disapprove/<int:user_id>', methods=['POST'])
@login_required
def disapprove_user(user_id):
    user = User.query.get_or_404(user_id)
    
    user.is_approved = False
    db.session.commit()
    
    # Notify user (always write disapproval status event)
    notification = Notification(
        user_id=user.id,
        title='Account Disapproved',
        message='Your account has been disapproved. Please contact support for more information.',
        notification_type='account_disapproved'
    )
    db.session.add(notification)
    db.session.commit()

    # Email notify seller/rider disapproval (non-blocking).
    email_sent = _send_account_disapproved_email(user)
    if user.user_type in ['seller', 'rider'] and not email_sent:
        flash('User disapproved, but disapproval email could not be sent.', 'warning')
    
    flash(f'User {user.first_name} {user.last_name} has been disapproved.', 'success')
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting admin users
    if user.user_type == 'admin':
        flash('Cannot delete admin users.', 'error')
        return redirect(url_for('admin.users'))
    
    # Store user info for flash message before deletion
    user_name = f"{user.first_name} {user.last_name}"
    
    # Delete related records first to avoid foreign key constraints
    try:
        # Delete user's email verifications
        EmailVerification.query.filter_by(user_id=user.id).delete()
        
        # Delete user's notifications
        Notification.query.filter_by(user_id=user.id).delete()
        
        # Get chat rooms where user is involved
        user_chat_rooms = ChatRoom.query.filter(
            (ChatRoom.seller_id == user.id) | 
            (ChatRoom.rider_id == user.id) | 
            (ChatRoom.buyer_id == user.id)
        ).all()
        
        # Delete messages in those chat rooms first
        for chat_room in user_chat_rooms:
            ChatMessage.query.filter_by(chat_room_id=chat_room.id).delete()
        
        # Delete user's chat messages (as sender)
        ChatMessage.query.filter_by(sender_id=user.id).delete()
        
        # Now delete chat rooms where user is involved
        ChatRoom.query.filter(
            (ChatRoom.seller_id == user.id) | 
            (ChatRoom.rider_id == user.id) | 
            (ChatRoom.buyer_id == user.id)
        ).delete()
        
        # Delete user's products (if seller)
        if user.user_type == 'seller':
            Product.query.filter_by(seller_id=user.id).delete()
        
        # Delete user's orders (if buyer) - this will cascade to order items
        if user.user_type == 'buyer':
            Order.query.filter_by(buyer_id=user.id).delete()
        
        # Delete user's deliveries (if rider)
        if user.user_type == 'rider':
            Delivery.query.filter_by(rider_id=user.id).delete()
        
        # Delete user's commissions
        Commission.query.filter(
            (Commission.seller_id == user.id) | 
            (Commission.rider_id == user.id)
        ).delete()
        
        # Finally delete the user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User {user_name} has been deleted successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
        print(f"Error deleting user {user_id}: {e}")
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/products')
@login_required
def products():
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')
    
    query = Product.query
    
    if status_filter != 'all':
        query = query.filter(Product.status == status_filter)
    
    if search:
        query = query.filter(Product.name.contains(search))
    
    products = query.order_by(Product.created_at.desc()).all()
    
    return render_template('admin/products.html', 
                         products=products, 
                         current_status=status_filter,
                         current_search=search)

@admin_bp.route('/orders')
@login_required
def orders():
    status_filter = request.args.get('status', 'all')
    
    query = Order.query
    query = filter_orders_by_tab(query, status_filter)
    orders = query.order_by(Order.created_at.desc()).all()
    
    return render_template('admin/orders.html', orders=orders, current_status=status_filter)


@admin_bp.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    delivery = order.delivery
    rider_user = (
        User.query.get(delivery.rider_id)
        if delivery and delivery.rider_id
        else None
    )
    return render_template(
        'admin/order_detail.html',
        order=order,
        buyer=order.buyer,
        delivery=delivery,
        rider_user=rider_user,
        delivery_status_label=_delivery_status_label(
            delivery.status if delivery else None
        ),
        timeline=_order_timeline_entries(order, delivery),
        proof_of_delivery=_proof_of_delivery_dict(delivery),
        pickup_shops_summary=order_pickup_shop_labels(order),
    )


@admin_bp.route('/commissions')
@login_required
def commissions():
    period = request.args.get('period', 'month')
    
    # Get commission data based on period
    if period == 'day':
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=1)
    elif period == 'week':
        start_date = datetime.now().date() - timedelta(days=7)
        end_date = datetime.now().date() + timedelta(days=1)
    elif period == 'month':
        start_date = datetime.now().date().replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1)
    else:  # year
        start_date = datetime.now().date().replace(month=1, day=1)
        end_date = start_date.replace(year=start_date.year + 1)
    
    # Get commission data
    commission_data = db.session.query(
        func.date(Commission.created_at).label('date'),
        func.sum(Commission.platform_commission).label('total_commission')
    ).filter(
        Commission.created_at >= start_date,
        Commission.created_at < end_date
    ).group_by(func.date(Commission.created_at)).all()
    
    # Get total platform commission
    total_commission = db.session.query(func.sum(Commission.platform_commission)).filter(
        Commission.created_at >= start_date,
        Commission.created_at < end_date
    ).scalar() or 0
    
    return render_template('admin/commissions.html',
                         commission_data=commission_data,
                         total_commission=total_commission,
                         period=period)

@admin_bp.route('/advertisements')
@login_required
def advertisements():
    advertisements = Advertisement.query.order_by(Advertisement.created_at.desc()).all()
    return render_template('admin/advertisements.html', advertisements=advertisements)

@admin_bp.route('/advertisements/add', methods=['GET', 'POST'])
@login_required
def add_advertisement():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        discount_percentage = int(request.form['discount_percentage'])
        expires_at = request.form.get('expires_at')
        promo_raw = (request.form.get('promo_code') or '').strip()
        if promo_raw and not re.match(r'^[A-Za-z0-9_-]{2,64}$', promo_raw):
            flash('Promo code: use 2–64 characters (letters, numbers, dash or underscore only).', 'error')
            return render_template('admin/add_advertisement.html')
        promo_code = promo_raw.upper() if promo_raw else None
        if promo_code:
            taken = Advertisement.query.filter_by(promo_code=promo_code).first()
            if taken:
                flash('That promo code is already in use. Choose a different code.', 'error')
                return render_template('admin/add_advertisement.html')
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                os.makedirs(os.path.join('static/uploads/advertisements'), exist_ok=True)
                file.save(os.path.join('static/uploads/advertisements', filename))
                image_url = f"uploads/advertisements/{filename}"
        
        advertisement = Advertisement(
            title=title,
            description=description,
            discount_percentage=discount_percentage,
            image_url=image_url,
            promo_code=promo_code,
            expires_at=datetime.strptime(expires_at, '%Y-%m-%d') if expires_at else None
        )
        
        db.session.add(advertisement)
        db.session.commit()
        
        flash('Advertisement added successfully!', 'success')
        return redirect(url_for('admin.advertisements'))
    
    return render_template('admin/add_advertisement.html')

@admin_bp.route('/advertisements/toggle/<int:ad_id>', methods=['POST'])
@login_required
def toggle_advertisement(ad_id):
    advertisement = Advertisement.query.get_or_404(ad_id)
    advertisement.is_active = not advertisement.is_active
    db.session.commit()
    
    status = 'activated' if advertisement.is_active else 'deactivated'
    flash(f'Advertisement {status} successfully!', 'success')
    
    return redirect(url_for('admin.advertisements'))

@admin_bp.route('/advertisements/delete/<int:ad_id>', methods=['POST'])
@login_required
def delete_advertisement(ad_id):
    advertisement = Advertisement.query.get_or_404(ad_id)
    
    # Delete the associated image file if it exists
    if advertisement.image_url:
        try:
            import os
            image_path = os.path.join('static', advertisement.image_url)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"Warning: Could not delete image file: {e}")
    
    # Delete the advertisement from database
    db.session.delete(advertisement)
    db.session.commit()
    
    flash('Advertisement deleted successfully!', 'success')
    
    return redirect(url_for('admin.advertisements'))

@admin_bp.route('/chat-support')
@login_required
def chat_support():
    update_user_activity()  # Update admin activity when accessing chat support
    
    # Get all users except admins
    users = User.query.filter(User.user_type != 'admin').order_by(User.first_name, User.last_name).all()
    
    # Get all chat rooms where admin is involved
    admin_id = session.get('user_id')
    chat_rooms = ChatRoom.query.filter(
        (ChatRoom.seller_id == admin_id) |
        (ChatRoom.rider_id == admin_id) |
        (ChatRoom.buyer_id == admin_id)
    ).order_by(ChatRoom.created_at.desc()).all()
    
    # Get current chat room if specified
    current_room_id = request.args.get('room_id')
    current_room = None
    messages = []
    chat_user = None
    chat_user_time_diff = None
    
    now = datetime.utcnow()
    
    if current_room_id:
        current_room = ChatRoom.query.get(current_room_id)
        if current_room:
            messages = ChatMessage.query.filter_by(chat_room_id=current_room_id).order_by(ChatMessage.created_at.asc()).all()
            
            # Get the chat user (non-admin user in the chat)
            if current_room.buyer_id and current_room.buyer_id != admin_id:
                chat_user = User.query.get(current_room.buyer_id)
            elif current_room.seller_id and current_room.seller_id != admin_id:
                chat_user = User.query.get(current_room.seller_id)
            elif current_room.rider_id and current_room.rider_id != admin_id:
                chat_user = User.query.get(current_room.rider_id)
            
            if chat_user:
                chat_user_time_diff = (now - chat_user.last_active).total_seconds()
    
    # Calculate time differences for all users
    users_with_time = []
    for user in users:
        time_diff = (now - user.last_active).total_seconds()
        users_with_time.append({
            'user': user,
            'time_diff': time_diff
        })
    
    return render_template('admin/chat_support.html', 
                         users_with_time=users_with_time, 
                         chat_rooms=chat_rooms,
                         current_room=current_room,
                         messages=messages,
                         chat_user=chat_user,
                         chat_user_time_diff=chat_user_time_diff,
                         now=now)

@admin_bp.route('/chat-support/start-chat', methods=['POST'])
@login_required
def start_chat():
    user_id = request.json.get('user_id')
    admin_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required'})
    
    # Check if chat room already exists (check all possible combinations)
    existing_room = ChatRoom.query.filter(
        (ChatRoom.room_type == 'admin_support') &
        (
            # Admin as seller, user as buyer
            ((ChatRoom.seller_id == admin_id) & (ChatRoom.buyer_id == user_id)) |
            # Admin as buyer, user as seller  
            ((ChatRoom.seller_id == user_id) & (ChatRoom.buyer_id == admin_id)) |
            # Admin as rider, user as buyer
            ((ChatRoom.rider_id == admin_id) & (ChatRoom.buyer_id == user_id)) |
            # Admin as buyer, user as rider
            ((ChatRoom.rider_id == user_id) & (ChatRoom.buyer_id == admin_id)) |
            # Admin as seller, user as rider
            ((ChatRoom.seller_id == admin_id) & (ChatRoom.rider_id == user_id)) |
            # Admin as rider, user as seller
            ((ChatRoom.seller_id == user_id) & (ChatRoom.rider_id == admin_id))
        )
    ).first()
    
    if existing_room:
        return jsonify({'success': True, 'room_id': existing_room.id})
    
    # Create new chat room based on user type
    user = User.query.get(user_id)
    room_name = f"Admin Support - {user.first_name} {user.last_name}"
    
    # Create room based on user type
    if user.user_type == 'buyer':
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            buyer_id=user_id,
            seller_id=admin_id
        )
    elif user.user_type == 'seller':
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            seller_id=user_id,
            buyer_id=admin_id
        )
    elif user.user_type == 'rider':
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            rider_id=user_id,
            buyer_id=admin_id
        )
    else:
        # Default to buyer for unknown types
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            buyer_id=user_id,
            seller_id=admin_id
        )
    
    db.session.add(new_room)
    db.session.commit()
    
    return jsonify({'success': True, 'room_id': new_room.id})

@admin_bp.route('/chat-support/send-message', methods=['POST'])
@login_required
def send_message():
    room_id = request.json.get('room_id')
    message_text = request.json.get('message')
    sender_id = session.get('user_id')
    
    if not room_id or not message_text:
        return jsonify({'success': False, 'message': 'Room ID and message are required'})
    
    # Verify the admin is part of this chat room
    room = ChatRoom.query.get(room_id)
    if not room or (room.seller_id != sender_id and room.buyer_id != sender_id and room.rider_id != sender_id):
        return jsonify({'success': False, 'message': 'Unauthorized access to chat room'})
    
    # Create new message
    new_message = ChatMessage(
        chat_room_id=room_id,
        sender_id=sender_id,
        message=message_text,
        message_type='text'
    )
    
    db.session.add(new_message)
    db.session.commit()
    
    return jsonify({'success': True, 'message_id': new_message.id})

@admin_bp.route('/chat-support/get-messages/<int:room_id>')
@login_required
def get_messages(room_id):
    # Verify the admin is part of this chat room
    room = ChatRoom.query.get(room_id)
    admin_id = session.get('user_id')
    
    if not room or (room.seller_id != admin_id and room.buyer_id != admin_id and room.rider_id != admin_id):
        return jsonify({'success': False, 'message': 'Unauthorized access'})
    
    messages = ChatMessage.query.filter_by(chat_room_id=room_id).order_by(ChatMessage.created_at.asc()).all()
    
    messages_data = []
    for msg in messages:
        sender = User.query.get(msg.sender_id)
        messages_data.append({
            'id': msg.id,
            'message': msg.message,
            'sender_name': f"{sender.first_name} {sender.last_name}",
            'sender_type': sender.user_type,
            'is_admin': sender.user_type == 'admin',
            'created_at': format_ph_datetime(msg.created_at, '%Y-%m-%d %H:%M:%S') if msg.created_at else '',
            'is_read': msg.is_read
        })
    
    return jsonify({'success': True, 'messages': messages_data})

@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    if request.method == 'POST':
        user.first_name = request.form['first_name']
        user.last_name = request.form['last_name']
        user.contact_number = request.form['contact_number']
        user.address_region = request.form['address_region']
        user.address_province = request.form['address_province']
        user.address_city = request.form['address_city']
        user.address_barangay = request.form['address_barangay']
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                filename = secure_filename(file.filename)
                os.makedirs(os.path.join('static/uploads/profiles'), exist_ok=True)
                file.save(os.path.join('static/uploads/profiles', filename))
                user.profile_picture = f"uploads/profiles/{filename}"
        
        db.session.commit()
        session['user_name'] = f"{user.first_name} {user.last_name}"
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('admin.profile'))
    
    return render_template('admin/profile.html', user=user)

@admin_bp.route('/notifications')
@login_required
def notifications():
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    return render_template('admin/notifications.html', notifications=notifications)


@admin_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    notification.is_read = True
    db.session.commit()
    flash('Notification marked as read.', 'success')
    return redirect(url_for('admin.notifications'))


@admin_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('admin.notifications'))


@admin_bp.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    flash('Notification deleted.', 'success')
    return redirect(url_for('admin.notifications'))


@admin_bp.route('/notifications/delete-all', methods=['POST'])
@login_required
def delete_all_notifications():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash('All notifications deleted.', 'success')
    return redirect(url_for('admin.notifications'))
