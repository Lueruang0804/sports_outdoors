from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from database import (
    db,
    User,
    Order,
    Delivery,
    Notification,
    Commission,
    ChatRoom,
    ChatMessage,
    order_pickup_shop_labels,
)
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func
import os
import io
import secrets
import re
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from timezone_utils import isoformat_utc_z, format_ph_datetime, get_ph_time

rider_bp = Blueprint('rider', __name__)


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


def _get_rider_commission_analytics_data(user_id, period):
    start_date, end_date = _get_period_range(period)

    commission_rows = db.session.query(
        func.date(Commission.created_at).label('date'),
        func.coalesce(func.sum(Commission.rider_commission), 0).label('commission')
    ).filter(
        Commission.rider_id == user_id,
        Commission.created_at >= start_date,
        Commission.created_at < end_date
    ).group_by(func.date(Commission.created_at)).order_by(func.date(Commission.created_at)).all()

    deliveries_rows = db.session.query(
        func.date(Delivery.created_at).label('date'),
        func.count(Delivery.id).label('deliveries')
    ).filter(
        Delivery.rider_id == user_id,
        Delivery.status == 'delivered',
        Delivery.created_at >= start_date,
        Delivery.created_at < end_date
    ).group_by(func.date(Delivery.created_at)).order_by(func.date(Delivery.created_at)).all()

    commission_data = [{"date": str(r.date), "commission": float(r.commission or 0)} for r in commission_rows]
    deliveries_data = [{"date": str(r.date), "deliveries": int(r.deliveries or 0)} for r in deliveries_rows]
    total_commission = round(sum(item["commission"] for item in commission_data), 2)
    total_deliveries = sum(item["deliveries"] for item in deliveries_data)

    return {
        "period": period,
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "commission_data": commission_data,
        "deliveries_data": deliveries_data,
        "total_commission": total_commission,
        "total_deliveries": total_deliveries,
    }

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'rider':
            flash('Please login as a rider to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def _delivery_to_api(delivery):
    buyer = delivery.order.buyer if delivery.order else None
    buyer_name = ''
    buyer_phone = ''
    if buyer:
        buyer_name = f"{buyer.first_name} {buyer.last_name}".strip()
        buyer_phone = buyer.contact_number or ''
    order = delivery.order
    pickup_shop = order_pickup_shop_labels(order) if order else ''
    return {
        'id': delivery.id,
        'order_id': delivery.order_id,
        'order_number': delivery.order.order_number if delivery.order else '',
        'buyer_name': buyer_name,
        'buyer_phone': buyer_phone,
        'pickup_shop': pickup_shop,
        'pickup_address': delivery.pickup_address or '',
        'delivery_address': delivery.delivery_address or '',
        'commission_amount': float(delivery.commission_amount or 0),
        'status': delivery.status,
        'created_at': isoformat_utc_z(delivery.created_at) if delivery.created_at else None,
        'updated_at': isoformat_utc_z(delivery.updated_at) if delivery.updated_at else None,
        'pod_image_url': (delivery.pod_image_url or '').strip(),
        'pod_remarks': (delivery.pod_remarks or '').strip(),
    }


def _seller_ids_for_order(order):
    ids = set()
    for oi in order.items:
        if oi.product:
            ids.add(oi.product.seller_id)
    return ids


def _apply_delivery_status_update(delivery, user_id, new_status):
    """
    Persist delivery status, keep Order.status in sync, notify buyer & sellers,
    and record commission when delivered. (Previously this logic was unreachable
    dead code inside _delivery_detail_payload.)
    """
    order = delivery.order
    if not order:
        delivery.status = new_status
        db.session.commit()
        return

    old_status = delivery.status
    if old_status == new_status:
        if (
            new_status == 'delivered'
            and order
            and (order.status or '').lower() not in ('delivered', 'cancelled', 'refunded')
        ):
            order.status = 'delivered'
            order.updated_at = datetime.utcnow()
            db.session.commit()
        return

    delivery.status = new_status
    now = datetime.utcnow()
    delivery.updated_at = now

    if new_status in ('picked_up', 'in_transit'):
        if order.status not in ('delivered', 'cancelled', 'refunded', 'shipped'):
            if order.status in ('pending', 'confirmed', 'preparing'):
                order.status = 'shipped'
                order.updated_at = now

    if new_status == 'picked_up':
        existing_chat = ChatRoom.query.filter_by(
            rider_id=user_id,
            buyer_id=order.buyer_id,
            order_id=delivery.order_id,
            room_type='rider_buyer',
        ).first()
        if not existing_chat:
            chat_room = ChatRoom(
                room_name=f"Delivery {order.order_number} - Rider & Buyer",
                room_type='rider_buyer',
                rider_id=user_id,
                buyer_id=order.buyer_id,
                order_id=delivery.order_id,
            )
            db.session.add(chat_room)
            db.session.flush()
            db.session.add(
                ChatMessage(
                    chat_room_id=chat_room.id,
                    sender_id=user_id,
                    message=(
                        "Hello! I'm your delivery rider. I've picked up your order "
                        "and I'm on my way. I'll keep you updated."
                    ),
                )
            )
        db.session.add(
            Notification(
                user_id=order.buyer_id,
                title='Package Picked Up',
                message=f'Your order {order.order_number} has been picked up and is on the way.',
                notification_type='delivery_update',
            )
        )
        rider = User.query.get(user_id)
        rlabel = (
            f'{rider.first_name or ""} {rider.last_name or ""}'.strip()
            if rider
            else 'Rider'
        )
        for sid in _seller_ids_for_order(order):
            db.session.add(
                Notification(
                    user_id=sid,
                    title='Order Picked Up',
                    message=(
                        f'Order {order.order_number} was picked up by {rlabel} and is en route to the buyer.'
                    ),
                    notification_type='order_update',
                )
            )

    elif new_status == 'in_transit':
        db.session.add(
            Notification(
                user_id=order.buyer_id,
                title='Package In Transit',
                message=f'Your order {order.order_number} is on the way to you.',
                notification_type='delivery_update',
            )
        )
        for sid in _seller_ids_for_order(order):
            db.session.add(
                Notification(
                    user_id=sid,
                    title='Order In Transit',
                    message=f'Order {order.order_number} is out for delivery.',
                    notification_type='order_update',
                )
            )

    elif new_status == 'delivered':
        order.status = 'delivered'
        order.updated_at = now

        if not Commission.query.filter_by(order_id=order.id).first():
            first = order.items[0] if order.items else None
            if first and first.product:
                db.session.add(
                    Commission(
                        order_id=order.id,
                        seller_id=first.product.seller_id,
                        rider_id=user_id,
                        platform_commission=Decimal(str(order.total_amount)) * Decimal('0.05'),
                        rider_commission=delivery.commission_amount or Decimal('0'),
                    )
                )

        db.session.add(
            Notification(
                user_id=order.buyer_id,
                title='Package Delivered',
                message=f'Your order {order.order_number} has been delivered. Enjoy!',
                notification_type='delivery_completed',
            )
        )
        for sid in _seller_ids_for_order(order):
            db.session.add(
                Notification(
                    user_id=sid,
                    title='Order Delivered',
                    message=f'Order {order.order_number} was delivered to the customer.',
                    notification_type='order_delivered',
                )
            )

    db.session.commit()


def _allowed_rider_profile_image(filename):
    ext = os.path.splitext((filename or '').lower())[1]
    return ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')


def _allowed_pod_image(filename):
    ext = os.path.splitext((filename or '').lower())[1]
    return ext in ('.png', '.jpg', '.jpeg')


def _rider_profile_payload(user):
    uid = user.id
    full_name = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    address_line = (
        f'{user.address_barangay}, {user.address_city}, {user.address_province}, {user.address_region}'
    ).strip(', ')
    deliveries_count = Delivery.query.filter_by(rider_id=uid).count()
    completed_deliveries = Delivery.query.filter_by(rider_id=uid, status='delivered').count()
    unread_notifications = Notification.query.filter_by(user_id=uid, is_read=False).count()
    messages_unread = 0
    rooms = ChatRoom.query.filter(
        ChatRoom.rider_id == uid,
        ChatRoom.is_active == True,  # noqa: E712
    ).all()
    for room in rooms:
        messages_unread += ChatMessage.query.filter(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.sender_id != uid,
            ChatMessage.is_read == False,  # noqa: E712
        ).count()

    total_commission = db.session.query(func.coalesce(func.sum(Commission.rider_commission), 0)).filter(
        Commission.rider_id == uid,
    ).scalar()

    return {
        'success': True,
        'email': user.email or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'full_name': full_name,
        'phone': user.contact_number or '',
        'address_line': address_line,
        'address_region': user.address_region or '',
        'address_province': user.address_province or '',
        'address_city': user.address_city or '',
        'address_barangay': user.address_barangay or '',
        'vehicle_type': user.vehicle_type or '',
        'vehicle_plate': user.vehicle_plate or '',
        'deliveries_count': deliveries_count,
        'completed_deliveries': completed_deliveries,
        'total_commission': float(total_commission or 0),
        'unread_notifications': unread_notifications,
        'messages_unread': messages_unread,
        'profile_picture': user.profile_picture or '',
    }


def _notification_category(notification):
    t = (notification.notification_type or '').lower()
    title = (notification.title or '').lower()
    msg = (notification.message or '').lower()
    if 'delivery' in t or 'delivery' in title or 'delivery' in msg or 'order' in msg:
        return 'deliveries'
    if 'commission' in t or 'payout' in msg or 'earning' in msg:
        return 'earnings'
    return 'system'


def _extract_order_number(text):
    if not text:
        return None
    patterns = [
        r'(ORD\d{8,})',
        r'(DEL-\d+)',
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _notification_delivery(notification):
    text = f'{notification.title or ""} {notification.message or ""}'
    order_number = _extract_order_number(text)
    if not order_number:
        return None
    order = Order.query.filter(func.lower(Order.order_number) == order_number.lower()).first()
    if not order:
        return None
    delivery = Delivery.query.filter_by(order_id=order.id).first()
    return delivery


def _notification_payload(notification):
    category = _notification_category(notification)
    delivery = _notification_delivery(notification)
    return {
        'id': notification.id,
        'title': notification.title or '',
        'message': notification.message or '',
        'is_read': notification.is_read,
        'notification_type': notification.notification_type or '',
        'category': category,
        'created_at': isoformat_utc_z(notification.created_at) if notification.created_at else None,
        'delivery_id': delivery.id if delivery else None,
        'order_number': delivery.order.order_number if delivery and delivery.order else None,
    }


def _upsert_rider_notification(user_id, title, message, notification_type):
    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
    existing = Notification.query.filter(
        Notification.user_id == user_id,
        Notification.notification_type == notification_type,
        Notification.message == message,
        Notification.created_at >= recent_cutoff
    ).first()
    if existing:
        return existing
    n = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type
    )
    db.session.add(n)
    return n


def _seed_rider_alerts(user_id):
    available = Delivery.query.filter_by(rider_id=None, status='pending').order_by(Delivery.created_at.desc()).limit(5).all()
    active = Delivery.query.filter(
        Delivery.rider_id == user_id,
        Delivery.status.in_(['assigned', 'picked_up', 'in_transit'])
    ).order_by(Delivery.updated_at.desc()).limit(5).all()
    recent_commissions = Commission.query.filter_by(rider_id=user_id).order_by(Commission.created_at.desc()).limit(3).all()

    seeded = 0
    for d in available:
        if not d.order:
            continue
        _upsert_rider_notification(
            user_id=user_id,
            title='New Delivery Assigned!',
            message=f'{d.order.order_number} is ready for pickup at {d.delivery_address}.',
            notification_type='delivery_assigned'
        )
        seeded += 1
    for d in active:
        if not d.order:
            continue
        _upsert_rider_notification(
            user_id=user_id,
            title='Delivery Status Updated',
            message=f'{d.order.order_number} is currently {d.status.replace("_", " ")}.',
            notification_type='delivery_update'
        )
        seeded += 1
    for c in recent_commissions:
        if not c.order:
            continue
        _upsert_rider_notification(
            user_id=user_id,
            title='Payment Received',
            message=f'Earnings of ₱{float(c.rider_commission or 0):.0f} for {c.order.order_number} has been credited.',
            notification_type='earning_update'
        )
        seeded += 1

    if seeded == 0:
        _upsert_rider_notification(
            user_id=user_id,
            title='Account Verified',
            message='Your rider account is active. You will receive delivery and earnings alerts here.',
            notification_type='system'
        )
    db.session.commit()


def _delivery_detail_payload(delivery):
    order = delivery.order
    if not order:
        return None
    buyer = order.buyer
    items = []
    for oi in order.items:
        items.append({
            'product_id': oi.product_id,
            'name': oi.product.name if oi.product else 'Item',
            'quantity': int(oi.quantity or 0),
            'price': float(oi.price or 0),
            'line_total': float((oi.price or 0) * (oi.quantity or 0)),
        })
    return {
        'delivery_id': delivery.id,
        'order_id': order.id,
        'order_number': order.order_number,
        'status': delivery.status,
        'buyer': {
            'name': f'{buyer.first_name if buyer else ""} {buyer.last_name if buyer else ""}'.strip(),
            'phone': buyer.contact_number if buyer else '',
        },
        'pickup_shop': order_pickup_shop_labels(order),
        'pickup_address': delivery.pickup_address or '',
        'delivery_address': delivery.delivery_address or '',
        'commission_amount': float(delivery.commission_amount or 0),
        'items': items,
        'assigned_at': isoformat_utc_z(delivery.updated_at) if delivery.updated_at else None,
        'pod_image_url': (delivery.pod_image_url or '').strip(),
        'pod_remarks': (delivery.pod_remarks or '').strip(),
    }


@rider_bp.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Get delivery statistics
    total_deliveries = Delivery.query.filter_by(rider_id=user_id).count()
    pending_deliveries = Delivery.query.filter_by(rider_id=user_id, status='pending').count()
    completed_deliveries = Delivery.query.filter_by(rider_id=user_id, status='delivered').count()
    
    # Calculate total commissions earned
    total_commissions = db.session.query(func.sum(Commission.rider_commission)).filter(
        Commission.rider_id == user_id
    ).scalar() or 0
    
    # Get monthly commissions
    monthly_commissions = db.session.query(func.sum(Commission.rider_commission)).filter(
        Commission.rider_id == user_id,
        Commission.created_at >= datetime.now().replace(day=1)
    ).scalar() or 0
    
    # Get recent deliveries
    recent_deliveries = Delivery.query.filter_by(rider_id=user_id).order_by(
        Delivery.created_at.desc()
    ).limit(5).all()
    
    # Get unread notifications
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    
    return render_template('rider/dashboard.html',
                         user=user,
                         total_deliveries=total_deliveries,
                         pending_deliveries=pending_deliveries,
                         completed_deliveries=completed_deliveries,
                         total_commissions=total_commissions,
                         monthly_commissions=monthly_commissions,
                         recent_deliveries=recent_deliveries,
                         unread_notifications=unread_notifications)

@rider_bp.route('/deliveries')
@login_required
def deliveries():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')
    
    query = Delivery.query.filter_by(rider_id=user_id)
    
    if status_filter != 'all':
        query = query.filter(Delivery.status == status_filter)
    
    deliveries = query.order_by(Delivery.created_at.desc()).all()
    
    return render_template('rider/deliveries.html', 
                         deliveries=deliveries, 
                         current_status=status_filter)


@rider_bp.route('/api/deliveries')
@login_required
def deliveries_api():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')

    query = Delivery.query.filter_by(rider_id=user_id)
    if status_filter != 'all':
        query = query.filter(Delivery.status == status_filter)

    deliveries = query.order_by(Delivery.created_at.desc()).all()
    return jsonify({
        'success': True,
        'deliveries': [_delivery_to_api(d) for d in deliveries],
    })

@rider_bp.route('/deliveries/available')
@login_required
def available_deliveries():
    # Get deliveries that are not yet assigned to any rider
    available_deliveries = Delivery.query.filter_by(rider_id=None, status='pending').order_by(
        Delivery.created_at.desc()
    ).all()
    
    return render_template('rider/available_deliveries.html', 
                         available_deliveries=available_deliveries)


@rider_bp.route('/api/deliveries/available')
@login_required
def available_deliveries_api():
    available_deliveries = Delivery.query.filter_by(
        rider_id=None,
        status='pending'
    ).order_by(Delivery.created_at.desc()).all()
    return jsonify({
        'success': True,
        'deliveries': [_delivery_to_api(d) for d in available_deliveries],
    })

@rider_bp.route('/deliveries/assign/<int:delivery_id>', methods=['POST'])
@login_required
def assign_delivery(delivery_id):
    user_id = session['user_id']
    delivery = Delivery.query.get_or_404(delivery_id)
    
    if delivery.rider_id is not None:
        flash('This delivery is already assigned to another rider.', 'warning')
        return redirect(url_for('rider.available_deliveries'))
    
    delivery.rider_id = user_id
    delivery.status = 'assigned'
    db.session.commit()
    
    # Notify buyer
    notification = Notification(
        user_id=delivery.order.buyer_id,
        title='Delivery Assigned',
        message=f'Your order {delivery.order.order_number} has been assigned to a rider.',
        notification_type='delivery_assigned'
    )
    db.session.add(notification)
    db.session.commit()
    
    flash('Delivery assigned successfully!', 'success')
    return redirect(url_for('rider.deliveries'))


@rider_bp.route('/api/deliveries/assign/<int:delivery_id>', methods=['POST'])
@login_required
def assign_delivery_api(delivery_id):
    user_id = session['user_id']
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.rider_id is not None:
        return jsonify({
            'success': False,
            'message': 'This delivery is already assigned to another rider.',
        }), 409

    delivery.rider_id = user_id
    delivery.status = 'assigned'
    db.session.commit()

    notification = Notification(
        user_id=delivery.order.buyer_id,
        title='Delivery Assigned',
        message=f'Your order {delivery.order.order_number} has been assigned to a rider.',
        notification_type='delivery_assigned'
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Delivery assigned successfully.',
        'delivery': _delivery_to_api(delivery),
    })

@rider_bp.route('/deliveries/<int:delivery_id>/update-status', methods=['POST'])
@login_required
def update_delivery_status(delivery_id):
    user_id = session['user_id']
    new_status = request.form['status']

    if new_status == 'delivered':
        flash(
            'Marking as delivered requires uploading proof of delivery (POD). '
            'Use “Mark as Delivered + Upload POD” on an In Transit order.',
            'warning',
        )
        return redirect(request.referrer or url_for('rider.deliveries'))

    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=user_id).first_or_404()
    _apply_delivery_status_update(delivery, user_id, new_status)
    flash('Delivery status updated successfully!', 'success')

    return redirect(url_for('rider.deliveries'))


@rider_bp.route('/deliveries/<int:delivery_id>/complete-with-pod', methods=['POST'])
@login_required
def complete_delivery_with_pod(delivery_id):
    user_id = session['user_id']
    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=user_id).first_or_404()
    if delivery.status != 'in_transit':
        flash('POD upload is only available when the delivery is In Transit.', 'error')
        return redirect(request.referrer or url_for('rider.deliveries'))

    confirm = (request.form.get('confirm_delivery') or '').strip().lower()
    if confirm not in ('1', 'on', 'true', 'yes'):
        flash('Please confirm that the order was delivered to the customer.', 'warning')
        return redirect(request.referrer or url_for('rider.deliveries'))

    file = request.files.get('pod_image')
    if not file or not file.filename:
        flash('Please choose a POD image (.png, .jpg, or .jpeg).', 'error')
        return redirect(request.referrer or url_for('rider.deliveries'))

    orig_name = secure_filename(file.filename)
    if not orig_name or not _allowed_pod_image(orig_name):
        flash('Invalid file type. Only .png, .jpg, and .jpeg are allowed.', 'error')
        return redirect(request.referrer or url_for('rider.deliveries'))

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_bytes = 8 * 1024 * 1024
    if size > max_bytes:
        flash('Image must be 8 MB or smaller.', 'error')
        return redirect(request.referrer or url_for('rider.deliveries'))
    if size == 0:
        flash('The selected file is empty.', 'error')
        return redirect(request.referrer or url_for('rider.deliveries'))

    ext = os.path.splitext(orig_name)[1].lower() or '.jpg'
    unique = f'{secrets.token_hex(16)}{ext}'
    upload_dir = os.path.join('static', 'uploads', 'pod')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, unique)
    file.save(save_path)

    remarks = (request.form.get('remarks') or '').strip()
    if len(remarks) > 2000:
        remarks = remarks[:2000]

    delivery.pod_image_url = f'uploads/pod/{unique}'
    delivery.pod_remarks = remarks or None
    _apply_delivery_status_update(delivery, user_id, 'delivered')
    flash('Delivery completed and POD saved successfully.', 'success')
    return redirect(url_for('rider.deliveries', status='delivered'))


@rider_bp.route('/api/deliveries/<int:delivery_id>/update-status', methods=['POST'])
@login_required
def update_delivery_status_api(delivery_id):
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    new_status = (payload.get('status') or request.form.get('status') or '').strip()
    allowed = {'assigned', 'picked_up', 'in_transit'}
    if new_status not in allowed:
        return jsonify({
            'success': False,
            'message': 'Invalid delivery status.',
        }), 400

    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=user_id).first_or_404()
    _apply_delivery_status_update(delivery, user_id, new_status)
    return jsonify({
        'success': True,
        'message': 'Delivery status updated successfully.',
        'delivery': _delivery_to_api(delivery),
    })


def _complete_delivery_with_pod_core(delivery_id, user_id):
    """Shared validation + save for HTML and JSON riders. Returns (delivery, None) or (None, error_msg)."""
    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=user_id).first()
    if not delivery:
        return None, 'Delivery not found.'
    if delivery.status != 'in_transit':
        return None, 'POD upload is only allowed when status is in_transit.'
    return delivery, None


@rider_bp.route('/api/deliveries/<int:delivery_id>/complete-with-pod', methods=['POST'])
@login_required
def complete_delivery_with_pod_api(delivery_id):
    user_id = session['user_id']
    delivery, err = _complete_delivery_with_pod_core(delivery_id, user_id)
    if err:
        code = 404 if err == 'Delivery not found.' else 400
        return jsonify({'success': False, 'message': err}), code

    payload = request.get_json(silent=True) or {}
    confirm = (
        (request.form.get('confirm_delivery') or '')
        or (payload.get('confirm_delivery') or '')
    ).strip().lower()
    if confirm not in ('1', 'on', 'true', 'yes'):
        return jsonify({
            'success': False,
            'message': 'confirm_delivery must be set (e.g. confirm_delivery=1).',
        }), 400

    file = request.files.get('pod_image')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Missing pod_image file.'}), 400

    orig_name = secure_filename(file.filename)
    if not orig_name or not _allowed_pod_image(orig_name):
        return jsonify({
            'success': False,
            'message': 'Invalid file type. Only .png, .jpg, and .jpeg are allowed.',
        }), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_bytes = 8 * 1024 * 1024
    if size > max_bytes:
        return jsonify({'success': False, 'message': 'Image must be 8 MB or smaller.'}), 400
    if size == 0:
        return jsonify({'success': False, 'message': 'Empty file.'}), 400

    ext = os.path.splitext(orig_name)[1].lower() or '.jpg'
    unique = f'{secrets.token_hex(16)}{ext}'
    upload_dir = os.path.join('static', 'uploads', 'pod')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, unique)
    file.save(save_path)

    remarks = (request.form.get('remarks') or payload.get('remarks') or '').strip()
    if len(remarks) > 2000:
        remarks = remarks[:2000]

    delivery.pod_image_url = f'uploads/pod/{unique}'
    delivery.pod_remarks = remarks or None
    _apply_delivery_status_update(delivery, user_id, 'delivered')
    return jsonify({
        'success': True,
        'message': 'Delivery completed and POD saved.',
        'delivery': _delivery_to_api(delivery),
    })

@rider_bp.route('/commissions')
@login_required
def commissions():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'
    analytics = _get_rider_commission_analytics_data(user_id, period)
    start_date, end_date = _get_period_range(period)
    
    # Get commission data
    commissions = Commission.query.filter(
        Commission.rider_id == user_id,
        Commission.created_at >= start_date,
        Commission.created_at < end_date
    ).order_by(Commission.created_at.desc()).all()
    
    return render_template('rider/commissions.html',
                         commissions=commissions,
                         total_commission=analytics['total_commission'],
                         commission_data=analytics['commission_data'],
                         deliveries_data=analytics['deliveries_data'],
                         period=period)


@rider_bp.route('/commissions/data')
@login_required
def commissions_data():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'
    return jsonify(_get_rider_commission_analytics_data(user_id, period))


@rider_bp.route('/api/commissions/data')
@login_required
def rider_api_commissions_data():
    """Same JSON as `/rider/commissions/data` — mobile calls `/rider/api/commissions/data`."""
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'
    return jsonify(_get_rider_commission_analytics_data(user_id, period))


@rider_bp.route('/commissions/pdf')
@login_required
def commissions_pdf():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'

    analytics = _get_rider_commission_analytics_data(user_id, period)
    rider = User.query.get(user_id)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Rider Commission Analytics Report")
    y -= 24
    pdf.setFont("Helvetica", 11)
    rider_name = f"{rider.first_name} {rider.last_name}" if rider else "Unknown Rider"
    pdf.drawString(40, y, f"Rider: {rider_name}")
    y -= 16
    pdf.drawString(40, y, f"Period: {period.title()} ({analytics['start_date']} to {analytics['end_date']})")
    y -= 16
    pdf.drawString(40, y, f"Generated: {format_ph_datetime(get_ph_time(), '%Y-%m-%d %H:%M:%S')}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, "Selected Period Totals")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, f"Total Rider Commission: PHP {analytics['total_commission']:.2f}")
    y -= 14
    pdf.drawString(50, y, f"Delivered Orders: {analytics['total_deliveries']}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Daily Rider Commission")
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
        y -= 14

    y -= 16
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Daily Delivered Orders")
    y -= 18
    pdf.setFont("Helvetica", 10)
    if analytics['deliveries_data']:
        for row in analytics['deliveries_data']:
            if y < 60:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y, f"{row['date']}: {row['deliveries']} deliveries")
            y -= 14
    else:
        pdf.drawString(50, y, "No delivered orders for selected period.")

    pdf.save()
    buffer.seek(0)
    filename = f"rider_commission_report_{period}_{get_ph_time().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@rider_bp.route('/profile', methods=['GET', 'POST'])
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
        return redirect(url_for('rider.profile'))
    
    return render_template('rider/profile.html', user=user)


@rider_bp.route('/api/profile', methods=['GET', 'PUT'])
@login_required
def rider_profile_api():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    if request.method == 'PUT':
        payload = request.get_json(silent=True) or {}
        if 'first_name' in payload:
            user.first_name = (payload.get('first_name') or '').strip() or user.first_name
        if 'last_name' in payload:
            user.last_name = (payload.get('last_name') or '').strip() or user.last_name
        if 'contact_number' in payload or 'phone' in payload:
            pn = (payload.get('contact_number') or payload.get('phone') or '').strip()
            if pn:
                user.contact_number = pn
        if 'address_region' in payload:
            user.address_region = (payload.get('address_region') or '').strip()
        if 'address_province' in payload:
            user.address_province = (payload.get('address_province') or '').strip()
        if 'address_city' in payload:
            user.address_city = (payload.get('address_city') or '').strip()
        if 'address_barangay' in payload:
            user.address_barangay = (payload.get('address_barangay') or '').strip()
        if 'vehicle_type' in payload:
            user.vehicle_type = (payload.get('vehicle_type') or '').strip()
        if 'vehicle_plate' in payload:
            user.vehicle_plate = (payload.get('vehicle_plate') or '').strip()
        db.session.commit()
        session['user_name'] = f'{user.first_name} {user.last_name}'
        return jsonify({
            'success': True,
            'message': 'Profile updated.',
            'profile': _rider_profile_payload(user),
        })
    return jsonify(_rider_profile_payload(user))


@rider_bp.route('/api/profile/picture', methods=['POST', 'DELETE'])
@login_required
def rider_profile_picture_api():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    if request.method == 'DELETE':
        user.profile_picture = None
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Profile picture removed.',
            'profile': _rider_profile_payload(user),
        })

    if 'profile_picture' not in request.files:
        return jsonify({'success': False, 'message': 'Missing file field profile_picture.'}), 400
    file = request.files['profile_picture']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file selected.'}), 400

    filename = secure_filename(file.filename)
    if not filename or not _allowed_rider_profile_image(filename):
        return jsonify({'success': False, 'message': 'Unsupported format. Use JPG, PNG, GIF, or WebP.'}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_bytes = 5 * 1024 * 1024
    if size > max_bytes:
        return jsonify({'success': False, 'message': 'Image must be 5 MB or smaller.'}), 400
    if size == 0:
        return jsonify({'success': False, 'message': 'Empty file.'}), 400

    ext = os.path.splitext(filename)[1].lower() or '.jpg'
    unique = f'{secrets.token_hex(16)}{ext}'
    upload_dir = os.path.join('static', 'uploads', 'profiles')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, unique)
    file.save(save_path)
    user.profile_picture = f'uploads/profiles/{unique}'
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Profile picture updated.',
        'profile': _rider_profile_payload(user),
    })

@rider_bp.route('/notifications')
@login_required
def notifications():
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    return render_template('rider/notifications.html', notifications=notifications)


@rider_bp.route('/api/notifications', methods=['GET'])
@login_required
def rider_notifications_api():
    user_id = session['user_id']
    category = (request.args.get('category') or 'all').strip().lower()
    items = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(150).all()
    if not items:
        _seed_rider_alerts(user_id)
        items = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(150).all()
    payload = [_notification_payload(n) for n in items]
    if category in ('deliveries', 'earnings', 'system'):
        payload = [p for p in payload if p['category'] == category]
    return jsonify({'success': True, 'notifications': payload})


@rider_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def rider_notification_read_api(notification_id):
    user_id = session['user_id']
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    n.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@rider_bp.route('/api/notifications/<int:notification_id>/detail', methods=['GET'])
@login_required
def rider_notification_detail_api(notification_id):
    user_id = session['user_id']
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    delivery = _notification_delivery(n)
    return jsonify({
        'success': True,
        'notification': _notification_payload(n),
        'delivery': _delivery_detail_payload(delivery) if delivery else None,
    })


@rider_bp.route('/api/notifications/<int:notification_id>/action', methods=['POST'])
@login_required
def rider_notification_action_api(notification_id):
    user_id = session['user_id']
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    payload = request.get_json(silent=True) or {}
    action = (payload.get('action') or '').strip().lower()
    if action not in ('accept', 'decline'):
        return jsonify({'success': False, 'message': 'Invalid action.'}), 400

    delivery = _notification_delivery(n)
    if action == 'accept':
        if not delivery:
            return jsonify({'success': False, 'message': 'No delivery linked to this notification.'}), 404
        if delivery.rider_id is None:
            delivery.rider_id = user_id
            delivery.status = 'assigned'
            db.session.commit()
            buyer_notice = Notification(
                user_id=delivery.order.buyer_id,
                title='Delivery Assigned',
                message=f'Your order {delivery.order.order_number} has been assigned to a rider.',
                notification_type='delivery_assigned'
            )
            db.session.add(buyer_notice)
        elif delivery.rider_id != user_id:
            return jsonify({'success': False, 'message': 'Delivery already assigned to another rider.'}), 409

    n.is_read = True
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Accepted delivery.' if action == 'accept' else 'Notification declined.',
        'delivery': _delivery_detail_payload(delivery) if delivery else None,
    })


@rider_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    notification.is_read = True
    db.session.commit()
    flash('Notification marked as read.', 'success')
    return redirect(url_for('rider.notifications'))


@rider_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('rider.notifications'))


@rider_bp.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    flash('Notification deleted.', 'success')
    return redirect(url_for('rider.notifications'))


@rider_bp.route('/notifications/delete-all', methods=['POST'])
@login_required
def delete_all_notifications():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash('All notifications deleted.', 'success')
    return redirect(url_for('rider.notifications'))

@rider_bp.route('/chat-support')
@login_required
def chat_support():
    # This would integrate with a chat system
    # For now, return a placeholder
    return render_template('rider/chat_support.html')

@rider_bp.route('/chat')
@login_required
def chat():
    user_id = session['user_id']
    
    # Get chat rooms where user is rider
    chat_rooms = ChatRoom.query.filter_by(rider_id=user_id, is_active=True).order_by(ChatRoom.updated_at.desc()).all()
    
    return render_template('rider/chat.html', chat_rooms=chat_rooms)


def _peer_label_rider_room(room):
    if room.buyer_id:
        u = User.query.get(room.buyer_id)
        if u:
            return (f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email or 'Buyer')
    return room.room_name or 'Chat'


@rider_bp.route('/api/chat/rooms', methods=['GET'])
@login_required
def rider_chat_rooms_api():
    user_id = session['user_id']
    rooms = ChatRoom.query.filter(
        ChatRoom.rider_id == user_id,
        ChatRoom.is_active == True,  # noqa: E712
    ).order_by(ChatRoom.updated_at.desc()).all()
    payload = []
    for room in rooms:
        last = ChatMessage.query.filter_by(chat_room_id=room.id).order_by(ChatMessage.created_at.desc()).first()
        unread = ChatMessage.query.filter(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.sender_id != user_id,
            ChatMessage.is_read == False,  # noqa: E712
        ).count()
        payload.append({
            'id': room.id,
            'room_type': room.room_type,
            'peer_name': _peer_label_rider_room(room),
            'peer_role': 'buyer',
            'order_id': room.order_id,
            'last_message_preview': (
                (last.message[:120] + '…') if last and len(last.message) > 120 else (last.message if last else '')
            ),
            'updated_at': isoformat_utc_z(room.updated_at) if room.updated_at else None,
            'unread_count': unread,
        })
    return jsonify({'success': True, 'rooms': payload})


@rider_bp.route('/api/chat/<int:room_id>/messages', methods=['GET', 'POST'])
@login_required
def rider_chat_messages_api(room_id):
    user_id = session['user_id']
    room = ChatRoom.query.filter_by(id=room_id, rider_id=user_id).first()
    if not room:
        return jsonify({'success': False, 'message': 'Chat not found.'}), 404
    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        text = (payload.get('message') or '').strip()
        if not text:
            return jsonify({'success': False, 'message': 'Message cannot be empty.'}), 400
        msg = ChatMessage(
            chat_room_id=room_id,
            sender_id=user_id,
            message=text,
        )
        db.session.add(msg)
        room.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Sent.', 'id': msg.id})

    messages = ChatMessage.query.filter_by(chat_room_id=room_id).order_by(ChatMessage.created_at.asc()).all()
    for m in messages:
        if m.sender_id != user_id:
            m.is_read = True
    db.session.commit()
    return jsonify({
        'success': True,
        'peer_name': _peer_label_rider_room(room),
        'messages': [
            {
                'id': m.id,
                'message': m.message,
                'sender_id': m.sender_id,
                'is_mine': m.sender_id == user_id,
                'created_at': isoformat_utc_z(m.created_at) if m.created_at else None,
            }
            for m in messages
        ],
    })


@rider_bp.route('/api/chat/search-buyers', methods=['GET'])
@login_required
def rider_search_buyers_api():
    q = (request.args.get('q') or '').strip()
    user_id = session['user_id']
    query = User.query.filter(User.user_type == 'buyer')
    if q:
        like = f'%{q}%'
        query = query.filter(
            (User.first_name.ilike(like)) |
            (User.last_name.ilike(like)) |
            (User.email.ilike(like))
        )
    buyers = query.order_by(User.first_name.asc(), User.last_name.asc()).limit(25).all()
    return jsonify({
        'success': True,
        'buyers': [
            {
                'id': b.id,
                'name': f'{b.first_name or ""} {b.last_name or ""}'.strip() or b.email,
                'email': b.email or '',
                'phone': b.contact_number or '',
            }
            for b in buyers if b.id != user_id
        ],
    })


@rider_bp.route('/api/chat/start', methods=['POST'])
@login_required
def rider_start_chat_api():
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    buyer_id = payload.get('buyer_id')
    if not buyer_id:
        return jsonify({'success': False, 'message': 'buyer_id is required.'}), 400
    buyer = User.query.filter_by(id=buyer_id, user_type='buyer').first()
    if not buyer:
        return jsonify({'success': False, 'message': 'Buyer not found.'}), 404

    room = ChatRoom.query.filter_by(
        rider_id=user_id,
        buyer_id=buyer.id,
        room_type='rider_buyer',
        is_active=True,
    ).order_by(ChatRoom.updated_at.desc()).first()
    if not room:
        room = ChatRoom(
            room_name=f'Rider & Buyer - {buyer.first_name} {buyer.last_name}'.strip(),
            room_type='rider_buyer',
            rider_id=user_id,
            buyer_id=buyer.id,
            is_active=True,
        )
        db.session.add(room)
        db.session.commit()

    return jsonify({
        'success': True,
        'room_id': room.id,
        'peer_name': _peer_label_rider_room(room),
    })

@rider_bp.route('/chat/<int:chat_room_id>')
@login_required
def chat_room(chat_room_id):
    user_id = session['user_id']
    
    # Get chat room
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, rider_id=user_id).first_or_404()
    
    # Get messages
    messages = ChatMessage.query.filter_by(chat_room_id=chat_room_id).order_by(ChatMessage.created_at.asc()).all()
    
    # Mark messages as read
    for message in messages:
        if message.sender_id != user_id:
            message.is_read = True
    db.session.commit()
    
    return render_template('rider/chat_room.html', chat_room=chat_room, messages=messages)

@rider_bp.route('/chat/<int:chat_room_id>/send-message', methods=['POST'])
@login_required
def send_message(chat_room_id):
    user_id = session['user_id']
    message_text = request.form.get('message')
    
    if not message_text:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('rider.chat_room', chat_room_id=chat_room_id))
    
    # Verify user has access to this chat room
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, rider_id=user_id).first_or_404()
    
    # Create message
    message = ChatMessage(
        chat_room_id=chat_room_id,
        sender_id=user_id,
        message=message_text
    )
    db.session.add(message)
    
    # Update chat room timestamp
    chat_room.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return redirect(url_for('rider.chat_room', chat_room_id=chat_room_id))
