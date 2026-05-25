from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from database import db, User, Product, Order, OrderItem, Notification, Commission, Delivery, ChatRoom, ChatMessage, Review
from datetime import datetime, timedelta
from sqlalchemy import func, extract, or_
import os
import json
import time
import io
import secrets
from decimal import Decimal
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from timezone_utils import isoformat_utc_z, format_ph_datetime, get_ph_time
from database import effective_order_status, delete_product_and_dependencies
from category_utils import normalize_category
from upload_storage import subdir_abs, db_relative_path
from media_storage import save_product_image_file, save_product_image_bytes, resolve_product_image_url

seller_bp = Blueprint('seller', __name__)


def _seller_category_choices(user):
    """Same defaults as seller JSON API when registration list is empty."""
    cats = []
    if user and user.product_categories:
        try:
            cats = json.loads(user.product_categories)
            if not isinstance(cats, list):
                cats = []
        except json.JSONDecodeError:
            cats = []
    if not cats:
        cats = [
            'Fitness Equipment', 'Camping & Hiking Gear', 'Outdoor Gear', 'Team Sports',
            'Water Sports', 'Cycling', 'Running', 'Apparel', 'Footwear', 'Other',
        ]
    return [normalize_category(c) for c in cats]


def _allowed_seller_profile_image(filename):
    ext = os.path.splitext((filename or '').lower())[1]
    return ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')


def _peer_label_seller_room(room):
    if room.buyer_id:
        u = User.query.get(room.buyer_id)
        if u:
            return (f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email or 'Buyer')
    if room.rider_id:
        u = User.query.get(room.rider_id)
        if u:
            return (f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email or 'Rider')
    return room.room_name or 'Chat'


def _seller_peer_role(room):
    if room.buyer_id and room.room_type == 'buyer_seller':
        return 'buyer'
    if room.rider_id:
        return 'rider'
    return 'chat'


def _seller_profile_payload(user):
    uid = user.id
    full_name = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    address_line = (
        f'{user.address_barangay}, {user.address_city}, {user.address_province}, {user.address_region}'
    ).strip(', ')

    product_count = Product.query.filter_by(seller_id=uid).count()

    orders_count = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == uid
    ).distinct().count()

    seller_orders = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == uid
    ).distinct().all()
    total_sales = sum(float(o.total_amount) for o in seller_orders if o.status == 'delivered')

    reviews_received_count = db.session.query(func.count(Review.id)).join(Product).filter(
        Product.seller_id == uid
    ).scalar() or 0

    avg_q = db.session.query(func.avg(Review.rating)).join(Product).filter(Product.seller_id == uid).scalar()
    avg_rating = round(float(avg_q or 0), 2) if avg_q else 0.0

    unread_notifications = Notification.query.filter_by(user_id=uid, is_read=False).count()

    rooms = ChatRoom.query.filter(
        ChatRoom.seller_id == uid,
        ChatRoom.is_active == True,  # noqa: E712
    ).all()
    messages_unread = 0
    for room in rooms:
        messages_unread += ChatMessage.query.filter(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.sender_id != uid,
            ChatMessage.is_read == False,  # noqa: E712
        ).count()

    recent_reviews = db.session.query(Review, Product, User).join(
        Product, Review.product_id == Product.id
    ).join(User, Review.user_id == User.id).filter(
        Product.seller_id == uid
    ).order_by(Review.created_at.desc()).limit(40).all()

    received_reviews = []
    for rev, prod, reviewer in recent_reviews:
        received_reviews.append({
            'id': rev.id,
            'product_id': prod.id,
            'product_name': prod.name or '',
            'rating': rev.rating,
            'comment': rev.comment or '',
            'reviewer_name': (
                f'{reviewer.first_name or ""} {reviewer.last_name or ""}'.strip()
                or reviewer.email or 'Customer'
            ),
            'created_at': isoformat_utc_z(rev.created_at) if rev.created_at else None,
        })

    store_display = 'Sports & Outdoor'
    if user and (user.first_name or user.last_name):
        named = f'{user.first_name or ""} {user.last_name or ""}'.strip()
        if named:
            store_display = named

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
        'profile_picture': user.profile_picture or '',
        'store_name': store_display,
        'product_categories_json': user.product_categories or '[]',
        'product_count': product_count,
        'orders_count': orders_count,
        'total_sales': round(float(total_sales), 2),
        'reviews_received_count': int(reviews_received_count),
        'avg_rating': avg_rating,
        'unread_notifications': unread_notifications,
        'messages_unread': messages_unread,
        'received_reviews': received_reviews,
    }


def _apply_seller_inventory_search(query, search_term):
    s = (search_term or '').strip()
    if not s:
        return query
    pattern = f'%{s}%'
    return query.filter(or_(
        Product.name.ilike(pattern),
        Product.description.ilike(pattern),
        Product.category.ilike(pattern),
    ))


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'seller':
            flash('Please login as a seller to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def seller_api_required(f):
    """JSON 401 for mobile / API (no HTML redirect)."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'seller':
            return jsonify({'success': False, 'message': 'Please login as a seller.'}), 401
        return f(*args, **kwargs)
    return decorated_function


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
    elif period == '30d':
        end = now + timedelta(days=1)
        start = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period in ('90d', '3m'):
        end = now + timedelta(days=1)
        start = (now - timedelta(days=89)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def _get_sales_analytics_data(user_id, period):
    start_date, end_date = _get_period_range(period)

    # Seller-specific revenue (only order items belonging to this seller)
    sales_rows = db.session.query(
        func.date(Order.created_at).label('date'),
        func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0).label('total')
    ).join(OrderItem, Order.id == OrderItem.order_id).join(
        Product, Product.id == OrderItem.product_id
    ).filter(
        Product.seller_id == user_id,
        Order.status == 'delivered',
        Order.created_at >= start_date,
        Order.created_at < end_date
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()

    commission_rows = db.session.query(
        func.date(Commission.created_at).label('date'),
        func.coalesce(func.sum(Commission.platform_commission), 0).label('commission')
    ).filter(
        Commission.seller_id == user_id,
        Commission.created_at >= start_date,
        Commission.created_at < end_date
    ).group_by(func.date(Commission.created_at)).order_by(func.date(Commission.created_at)).all()

    sales_data = [
        {"date": str(row.date), "total": float(row.total or 0)}
        for row in sales_rows
    ]
    commission_data = [
        {"date": str(row.date), "commission": float(row.commission or 0)}
        for row in commission_rows
    ]

    total_sales = round(sum(item["total"] for item in sales_data), 2)
    total_commission = round(sum(item["commission"] for item in commission_data), 2)
    net_earnings = round(max(0.0, total_sales - total_commission), 2)

    qty_sum = func.coalesce(func.sum(OrderItem.quantity), 0).label('qty')
    rev_sum = func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0).label('rev')
    top_rows = db.session.query(
        Product.id,
        Product.name,
        Product.image_url,
        qty_sum,
        rev_sum,
    ).join(OrderItem, Product.id == OrderItem.product_id).join(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Product.seller_id == user_id,
        Order.status == 'delivered',
        Order.created_at >= start_date,
        Order.created_at < end_date,
    ).group_by(Product.id, Product.name, Product.image_url).order_by(rev_sum.desc()).limit(5).all()

    top_products = [
        {
            'product_id': int(r.id),
            'name': r.name or '',
            'image_url': r.image_url or '',
            'quantity_sold': int(r.qty or 0),
            'revenue': round(float(r.rev or 0), 2),
        }
        for r in top_rows
    ]

    return {
        "period": period,
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "sales_data": sales_data,
        "commission_data": commission_data,
        "total_sales": total_sales,
        "total_commission": total_commission,
        "net_earnings": net_earnings,
        "top_products": top_products,
    }


def _seller_average_rating(user_id):
    avg = db.session.query(func.avg(Review.rating)).join(Product).filter(
        Product.seller_id == user_id
    ).scalar()
    if avg is None:
        return 0.0
    return round(float(avg), 1)


def _buyer_short_name(user):
    if not user:
        return 'Customer'
    fn_parts = (user.first_name or '').strip().split()
    ln = (user.last_name or '').strip()
    if fn_parts and ln:
        return f'{fn_parts[0]} {ln[0].upper()}.'
    if fn_parts:
        return fn_parts[0]
    return (user.email or '?').split('@')[0]


def _order_status_pill_key(status):
    if status == 'delivered':
        return 'success'
    if status == 'cancelled' or status == 'refunded':
        return 'danger'
    if status in ('pending', 'confirmed'):
        return 'warning'
    return 'info'


def _weekly_sales_bars(user_id):
    """Seven consecutive days aligned with website weekly analytics window."""
    week = _get_sales_analytics_data(user_id, 'week')
    sales_by_date = {row['date']: float(row['total']) for row in week['sales_data']}
    start_s = datetime.strptime(week['start_date'], '%Y-%m-%d')
    bars = []
    for i in range(7):
        dt = start_s + timedelta(days=i)
        ds = dt.strftime('%Y-%m-%d')
        bars.append({
            'label': dt.strftime('%a'),
            'date': ds,
            'total': sales_by_date.get(ds, 0.0),
        })
    return bars


def _seller_recent_orders_payload(user_id, limit=8):
    orders = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == user_id
    ).distinct().order_by(Order.created_at.desc()).limit(limit).all()
    rows = []
    for order in orders:
        buyer = order.buyer
        short_name = _buyer_short_name(buyer)
        item = db.session.query(OrderItem).join(Product).filter(
            OrderItem.order_id == order.id,
            Product.seller_id == user_id
        ).first()
        product_label = item.product.name if item and item.product else 'Order'
        rows.append({
            'order_id': order.id,
            'order_number': order.order_number,
            'customer_short': short_name,
            'product_name': product_label,
            'amount': float(order.total_amount),
            'status': effective_order_status(order),
            'pill': _order_status_pill_key(effective_order_status(order)),
        })
    return rows


@seller_bp.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Get sales statistics
    total_products = Product.query.filter_by(seller_id=user_id).count()
    active_products = Product.query.filter_by(seller_id=user_id, status='active').count()
    
    # Get orders for this seller's products
    seller_orders = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == user_id
    ).distinct().all()
    
    total_orders = len(seller_orders)
    pending_orders = len([o for o in seller_orders if o.status in ['pending', 'confirmed', 'preparing']])
    
    # Calculate total sales
    total_sales = sum(order.total_amount for order in seller_orders if order.status == 'delivered')
    
    # Get recent orders
    recent_orders = seller_orders[:5]
    
    # Get unread notifications
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    
    return render_template('seller/dashboard.html',
                         user=user,
                         total_products=total_products,
                         active_products=active_products,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         total_sales=total_sales,
                         recent_orders=recent_orders,
                         unread_notifications=unread_notifications)

@seller_bp.route('/products')
@login_required
def products():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')
    search = (request.args.get('search', '') or '').strip()
    low_stock_flag = request.args.get('low_stock', '').lower() in ('1', 'true', 'yes')

    query = Product.query.filter_by(seller_id=user_id)

    if low_stock_flag:
        query = query.filter(Product.stock_quantity <= 5, Product.status == 'active')
    elif status_filter != 'all':
        query = query.filter(Product.status == status_filter)

    query = _apply_seller_inventory_search(query, search)

    products = query.order_by(Product.created_at.desc()).all()

    return render_template(
        'seller/products.html',
        products=products,
        current_status=status_filter,
        current_search=search,
        current_low_stock=low_stock_flag,
    )

@seller_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    user_id = session['user_id']
    user = User.query.get(user_id)
    categories = _seller_category_choices(user)

    if request.method == 'POST':
        intent = request.form.get('save_intent', 'publish')
        is_draft = intent == 'draft'

        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        category = normalize_category((request.form.get('category') or '').strip())

        try:
            price = float(request.form.get('price') or 0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            stock_quantity = int(request.form.get('stock_quantity') or 0)
        except (TypeError, ValueError):
            stock_quantity = 0

        if is_draft:
            if not name:
                flash('Add a product name to save a draft.', 'warning')
                return render_template('seller/add_product.html', categories=categories, prefill=request.form)
            if not description:
                description = ''
            if not category:
                category = categories[0] if categories else 'Other'
            price = max(0.0, float(price))
            stock_quantity = max(0, stock_quantity)
            status = 'inactive'
        else:
            if not name or not description or not category:
                flash('Please complete all fields to publish a live product.', 'danger')
                return render_template('seller/add_product.html', categories=categories, prefill=request.form)
            if price < 0:
                flash('Price cannot be negative.', 'danger')
                return render_template('seller/add_product.html', categories=categories, prefill=request.form)
            stock_quantity = max(0, stock_quantity)
            status = 'active'

        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                image_url = save_product_image_file(file)
                if image_url:
                    print(f"SUCCESS: Image uploaded: {image_url}")
                else:
                    flash('Failed to upload image. A placeholder will be used if needed.', 'warning')

        if not image_url:
            image_url = _seller_placeholder_image(name)

        product = Product(
            name=name,
            description=description,
            price=price,
            category=category,
            stock_quantity=stock_quantity,
            image_url=image_url,
            seller_id=user_id,
            status=status,
        )

        db.session.add(product)
        db.session.commit()

        if is_draft:
            flash('Draft saved. You can finish and publish it from My Products.', 'success')
        else:
            flash('Product added successfully!', 'success')
        return redirect(url_for('seller.products'))

    return render_template('seller/add_product.html', categories=categories, prefill=None)

@seller_bp.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first_or_404()
    
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.category = normalize_category(request.form['category'])
        product.stock_quantity = int(request.form['stock_quantity'])
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                new_url = save_product_image_file(file)
                if new_url:
                    product.image_url = new_url
                    print(f"SUCCESS: Image uploaded: {product.image_url}")
                else:
                    flash('Failed to upload image. Product updated without new image.', 'warning')
        
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('seller.products'))
    
    user = User.query.get(user_id)
    categories = _seller_category_choices(user)

    return render_template('seller/edit_product.html', product=product, categories=categories)

@seller_bp.route('/products/delete/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first_or_404()
    
    # Check if product has orders
    has_orders = OrderItem.query.join(Product).filter(Product.id == product_id).first() is not None
    
    if has_orders:
        flash('Cannot delete product with existing orders. Archive it instead.', 'warning')
    else:
        try:
            delete_product_and_dependencies(product)
            db.session.commit()
            flash('Product deleted successfully!', 'success')
        except Exception:
            db.session.rollback()
            flash('Could not delete product. Please try again or archive it instead.', 'danger')
    
    return redirect(url_for('seller.products'))

@seller_bp.route('/products/archive/<int:product_id>', methods=['POST'])
@login_required
def archive_product(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first_or_404()
    
    product.status = 'archived'
    db.session.commit()
    flash('Product archived successfully!', 'success')
    
    return redirect(url_for('seller.products'))

@seller_bp.route('/products/retrieve/<int:product_id>', methods=['POST'])
@login_required
def retrieve_product(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first_or_404()

    was = product.status
    product.status = 'active'
    db.session.commit()
    if was == 'archived':
        flash('Product retrieved from archive.', 'success')
    elif was == 'inactive':
        flash('Draft published — product is now live.', 'success')
    else:
        flash('Product updated.', 'success')

    return redirect(url_for('seller.products'))

@seller_bp.route('/orders')
@login_required
def orders():
    user_id = session['user_id']
    
    # Get orders for this seller's products
    orders = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == user_id
    ).distinct().order_by(Order.created_at.desc()).all()
    
    # Get available riders for assignment
    available_riders = User.query.filter_by(user_type='rider', is_approved=True).all()
    
    return render_template('seller/orders.html', orders=orders, available_riders=available_riders)

@seller_bp.route('/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_order_status(order_id):
    user_id = session['user_id']
    new_status = request.form['status']
    
    # Get order items for this seller
    order_items = db.session.query(OrderItem).join(Product).filter(
        Product.seller_id == user_id,
        OrderItem.order_id == order_id
    ).all()
    
    if not order_items:
        flash('Order not found.', 'error')
        return redirect(url_for('seller.orders'))
    
    order = order_items[0].order
    
    # Update order status
    if new_status in ['confirmed', 'preparing', 'shipped']:
        order.status = new_status
        db.session.commit()
        
        # Notify buyer
        notification = Notification(
            user_id=order.buyer_id,
            title='Order Status Update',
            message=f'Your order {order.order_number} status has been updated to {new_status.title()}',
            notification_type='order_update'
        )
        db.session.add(notification)
        db.session.commit()
        
        flash('Order status updated successfully!', 'success')
    
    return redirect(url_for('seller.orders'))

def _perform_assign_rider(user_id, order_id, rider_id_raw):
    """
    Same logic for web form and mobile JSON. rider_id_raw: str/int/None.
    Returns dict: success + optional error / rider_name.
    """
    if rider_id_raw is None or rider_id_raw == '':
        return {'success': False, 'error': 'Please select a rider.'}
    try:
        rider_id_int = int(rider_id_raw)
    except (TypeError, ValueError):
        return {'success': False, 'error': 'Invalid rider.'}

    order_items = db.session.query(OrderItem).join(Product).filter(
        Product.seller_id == user_id,
        OrderItem.order_id == order_id
    ).all()
    if not order_items:
        return {'success': False, 'error': 'Order not found.'}

    order = order_items[0].order
    if order.status not in ('confirmed', 'preparing'):
        return {'success': False, 'error': 'Rider can only be assigned when the order is confirmed or preparing.'}

    delivery = Delivery.query.filter_by(order_id=order_id).first()
    if delivery and delivery.rider_id:
        return {'success': False, 'error': 'A rider is already assigned to this order.'}

    rider = User.query.get(rider_id_int)
    if not rider or rider.user_type != 'rider' or not getattr(rider, 'is_approved', False):
        return {'success': False, 'error': 'Invalid or unapproved rider.'}

    if not delivery:
        delivery = Delivery(
            order_id=order_id,
            status='pending',
            pickup_address=order.shipping_address,
            delivery_address=order.shipping_address,
            commission_amount=Decimal(str(order.total_amount)) * Decimal('0.05')
        )
        db.session.add(delivery)
        db.session.flush()

    delivery.rider_id = rider_id_int
    delivery.status = 'assigned'

    chat_room = ChatRoom.query.filter_by(
        seller_id=user_id,
        rider_id=rider_id_int,
        order_id=order_id,
        room_type='seller_rider'
    ).first()
    if not chat_room:
        chat_room = ChatRoom(
            room_name=f"Order {order.order_number} - Seller & Rider",
            room_type='seller_rider',
            seller_id=user_id,
            rider_id=rider_id_int,
            order_id=order_id
        )
        db.session.add(chat_room)

    db.session.add(Notification(
        user_id=rider_id_int,
        title='New Delivery Assignment',
        message=f'You have been assigned to deliver order {order.order_number}',
        notification_type='delivery_assigned'
    ))
    db.session.add(Notification(
        user_id=order.buyer_id,
        title='Delivery Update',
        message=f'Your order {order.order_number} has been assigned to rider {rider.first_name} {rider.last_name}',
        notification_type='delivery_update'
    ))
    db.session.commit()

    rname = f'{rider.first_name or ""} {rider.last_name or ""}'.strip() or 'Rider'
    return {'success': True, 'rider_name': rname}


@seller_bp.route('/orders/<int:order_id>/assign-rider', methods=['POST'])
@login_required
def assign_rider(order_id):
    user_id = session['user_id']
    result = _perform_assign_rider(user_id, order_id, request.form.get('rider_id'))
    if result['success']:
        flash(f"Rider {result['rider_name']} assigned successfully!", 'success')
    else:
        flash(result.get('error') or 'Assignment failed.', 'error')
    return redirect(url_for('seller.orders'))

@seller_bp.route('/sales-report')
@login_required
def sales_report():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'
    analytics = _get_sales_analytics_data(user_id, period)

    return render_template('seller/sales_report.html',
                         sales_data=analytics['sales_data'],
                         commission_data=analytics['commission_data'],
                         total_sales=analytics['total_sales'],
                         total_commission=analytics['total_commission'],
                         period=period)


@seller_bp.route('/sales-report/data')
@login_required
def sales_report_data():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'
    return jsonify(_get_sales_analytics_data(user_id, period))


@seller_bp.route('/api/dashboard')
@seller_api_required
def seller_dashboard_api():
    user_id = session['user_id']
    user = User.query.get(user_id)
    seller_orders = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == user_id
    ).distinct().all()
    total_orders = len(seller_orders)
    total_sales = sum(float(o.total_amount) for o in seller_orders if o.status == 'delivered')
    total_products = Product.query.filter_by(seller_id=user_id).count()
    unread = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    rating = _seller_average_rating(user_id)

    store_display = 'Sports & Outdoor'
    if user and (user.first_name or user.last_name):
        named = f'{user.first_name or ""} {user.last_name or ""}'.strip()
        if named:
            store_display = named

    return jsonify({
        'success': True,
        'store_name': store_display,
        'seller_email': user.email if user else '',
        'total_sales': round(total_sales, 2),
        'order_count': total_orders,
        'product_count': total_products,
        'avg_rating': rating,
        'unread_notifications': unread,
        'weekly_sales': _weekly_sales_bars(user_id),
        'recent_orders': _seller_recent_orders_payload(user_id, limit=8),
    })


ALLOWED_SELLER_STATUS = {'confirmed', 'preparing', 'shipped', 'cancelled'}


def _order_to_seller_list_json(user_id, order):
    buyer = order.buyer
    item = db.session.query(OrderItem).join(Product).filter(
        OrderItem.order_id == order.id,
        Product.seller_id == user_id
    ).first()
    item_count = db.session.query(OrderItem).join(Product).filter(
        OrderItem.order_id == order.id,
        Product.seller_id == user_id
    ).count()
    delivery = order.delivery
    rider_id = None
    rider_name = None
    rider_phone = None
    delivery_status = None
    if delivery:
        delivery_status = delivery.status
        if delivery.rider_id:
            rider_id = delivery.rider_id
            ru = User.query.get(delivery.rider_id)
            if ru:
                rider_name = f'{ru.first_name or ""} {ru.last_name or ""}'.strip()
                rider_phone = ru.contact_number or ''

    can_assign = (
        order.status in ('confirmed', 'preparing')
        and not (delivery and delivery.rider_id)
    )

    return {
        'id': order.id,
        'order_number': order.order_number,
        'total_amount': float(order.total_amount),
        'status': effective_order_status(order),
        'item_count': item_count,
        'primary_product_name': item.product.name if item and item.product else '',
        'primary_product_id': item.product_id if item else None,
        'seller_display_name': _buyer_short_name(buyer),
        'buyer_full_name': f'{buyer.first_name or ""} {buyer.last_name or ""}'.strip() if buyer else '',
        'created_at': isoformat_utc_z(order.created_at) if order.created_at else None,
        'payment_method': order.payment_method or '',
        'shipping_address': order.shipping_address or '',
        'delivery_status': delivery_status,
        'rider_id': rider_id,
        'rider_name': rider_name or '',
        'rider_phone': rider_phone or '',
        'can_assign_rider': can_assign,
        'can_approve': order.status == 'pending',
        'can_reject': order.status == 'pending',
        'can_mark_shipped': order.status in ('confirmed', 'preparing'),
    }


def _order_to_seller_detail_json(user_id, order):
    base = _order_to_seller_list_json(user_id, order)
    lines = []
    for oi in order.items:
        p = oi.product
        if not p or p.seller_id != user_id:
            continue
        lines.append({
            'product_id': p.id,
            'product_name': p.name or '',
            'quantity': oi.quantity,
            'unit_price': float(oi.price),
            'line_total': round(float(oi.price) * oi.quantity, 2),
            'image_url': p.image_url or '',
        })
    subtotal = round(sum(x['line_total'] for x in lines), 2)
    base['line_items'] = lines
    base['seller_subtotal'] = subtotal
    base['updated_at'] = isoformat_utc_z(order.updated_at) if order.updated_at else None
    d = order.delivery
    if d and (getattr(d, 'pod_image_url', None) or '').strip():
        base['pod_image_url'] = d.pod_image_url.strip()
        base['pod_remarks'] = (getattr(d, 'pod_remarks', None) or '').strip()
    else:
        base['pod_image_url'] = ''
        base['pod_remarks'] = ''
    return base


@seller_bp.route('/api/sales-analytics')
@seller_api_required
def seller_sales_analytics_api():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    allowed = ['day', 'week', 'month', 'year', '30d', '90d', '3m']
    if period not in allowed:
        period = 'month'
    data = dict(_get_sales_analytics_data(user_id, period))
    data['success'] = True
    return jsonify(data)


@seller_bp.route('/api/orders')
@seller_api_required
def seller_orders_api():
    user_id = session['user_id']
    orders = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == user_id
    ).distinct().order_by(Order.created_at.desc()).all()
    payload = [_order_to_seller_list_json(user_id, o) for o in orders]
    return jsonify({'success': True, 'orders': payload})


@seller_bp.route('/api/orders/<int:order_id>', methods=['GET'])
@seller_api_required
def seller_order_detail_api(order_id):
    user_id = session['user_id']
    order_items = db.session.query(OrderItem).join(Product).filter(
        Product.seller_id == user_id,
        OrderItem.order_id == order_id
    ).first()
    if not order_items:
        return jsonify({'success': False, 'error': 'Order not found.'}), 404
    order = Order.query.get_or_404(order_id)
    return jsonify({'success': True, 'order': _order_to_seller_detail_json(user_id, order)})


@seller_bp.route('/api/riders', methods=['GET'])
@seller_api_required
def seller_riders_api():
    riders = User.query.filter_by(user_type='rider', is_approved=True).order_by(
        User.first_name, User.last_name
    ).all()
    payload = [
        {
            'id': r.id,
            'name': f'{r.first_name or ""} {r.last_name or ""}'.strip() or f'Rider #{r.id}',
            'phone': r.contact_number or '',
        }
        for r in riders
    ]
    return jsonify({'success': True, 'riders': payload})


@seller_bp.route('/api/orders/<int:order_id>/assign-rider', methods=['POST'])
@seller_api_required
def seller_assign_rider_api(order_id):
    user_id = session['user_id']
    body = request.get_json(silent=True) or {}
    rider_id = body.get('rider_id')
    if rider_id is None:
        rider_id = request.form.get('rider_id')
    result = _perform_assign_rider(user_id, order_id, rider_id)
    if result['success']:
        return jsonify({'success': True, 'message': f"Rider {result['rider_name']} assigned.", 'rider_name': result['rider_name']})
    return jsonify({'success': False, 'error': result.get('error') or 'Assignment failed.'}), 400


def _seller_apply_order_status(user_id, order_id, new_status):
    if new_status not in ALLOWED_SELLER_STATUS:
        return {'success': False, 'error': 'Invalid status.'}

    order_items = db.session.query(OrderItem).join(Product).filter(
        Product.seller_id == user_id,
        OrderItem.order_id == order_id
    ).all()
    if not order_items:
        return {'success': False, 'error': 'Order not found.'}
    order = order_items[0].order
    cur = order.status

    allowed_next = {
        'pending': {'confirmed', 'preparing', 'shipped', 'cancelled'},
        'confirmed': {'preparing', 'shipped', 'cancelled'},
        'preparing': {'shipped', 'cancelled'},
    }
    if cur not in allowed_next or new_status not in allowed_next[cur]:
        return {'success': False, 'error': f'Cannot change status from {cur} to {new_status}.'}

    order.status = new_status
    order.updated_at = datetime.utcnow()

    label = new_status.replace('_', ' ').title()
    db.session.add(Notification(
        user_id=order.buyer_id,
        title='Order Status Update' if new_status != 'cancelled' else 'Order Cancelled',
        message=(
            f'Your order {order.order_number} has been cancelled.'
            if new_status == 'cancelled'
            else f'Your order {order.order_number} status has been updated to {label}'
        ),
        notification_type='order_update',
    ))
    db.session.commit()
    return {'success': True}


@seller_bp.route('/api/orders/<int:order_id>/update-status', methods=['POST'])
@seller_api_required
def seller_order_update_status_api(order_id):
    user_id = session['user_id']
    body = request.get_json(silent=True) or {}
    new_status = body.get('status')
    if not new_status and request.form.get('status'):
        new_status = request.form.get('status')
    result = _seller_apply_order_status(user_id, order_id, new_status)
    if result['success']:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': result.get('error')}), 400


def _product_to_seller_json(p):
    img = resolve_product_image_url(p.image_url, external=True) if p.image_url else ''
    return {
        'id': p.id,
        'name': p.name,
        'description': p.description or '',
        'price': float(p.price),
        'stock_quantity': p.stock_quantity,
        'status': p.status,
        'category': p.category,
        'image_url': img or '',
    }


@seller_bp.route('/api/categories', methods=['GET'])
@seller_api_required
def seller_categories_api():
    """Categories from seller registration (same as add_product form)."""
    user_id = session['user_id']
    user = User.query.get(user_id)
    cats = []
    if user and user.product_categories:
        try:
            cats = json.loads(user.product_categories)
            if not isinstance(cats, list):
                cats = []
        except json.JSONDecodeError:
            cats = []
    # Defaults when seller has no JSON list (matches typical onboarding)
    if not cats:
        cats = [
            'Fitness Equipment', 'Camping & Hiking Gear', 'Outdoor Gear', 'Team Sports',
            'Water Sports', 'Cycling', 'Running', 'Apparel', 'Footwear', 'Other',
        ]
    return jsonify({'success': True, 'categories': [normalize_category(c) for c in cats]})


@seller_bp.route('/api/products', methods=['GET', 'POST'])
@seller_api_required
def seller_products_api():
    user_id = session['user_id']
    if request.method == 'POST':
        return _seller_api_product_create(user_id)

    status_filter = (request.args.get('status') or 'all').strip()
    search = (request.args.get('search') or '').strip()
    low_stock = request.args.get('low_stock', '').lower() in ('1', 'true', 'yes')

    q = Product.query.filter_by(seller_id=user_id)
    if low_stock:
        q = q.filter(Product.stock_quantity <= 5, Product.status == 'active')
    elif status_filter and status_filter != 'all':
        q = q.filter(Product.status == status_filter)
    q = _apply_seller_inventory_search(q, search)
    products = q.order_by(Product.created_at.desc()).all()
    return jsonify({
        'success': True,
        'products': [_product_to_seller_json(p) for p in products],
    })


def _seller_save_uploaded_image(file_storage):
    """Returns Supabase public URL or uploads/products/... path."""
    return save_product_image_file(file_storage)


def _seller_placeholder_image(name):
    """Placeholder when no image; stored in Supabase or local uploads."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (300, 200), (240, 240, 240))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except Exception:
            font = ImageFont.load_default()
        text = name[:25] + "..." if len(name) > 25 else name
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = len(text) * 10, 20
        x = (300 - tw) // 2
        y = 90
        draw.text((x, y), text, fill=(100, 100, 100), font=font)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85)
        return save_product_image_bytes(buf.getvalue(), f'placeholder_{int(time.time())}.jpg')
    except Exception as e:
        print(f'ERROR: placeholder image: {e}')
        return None


def _seller_api_product_create(user_id):
    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    category = normalize_category((request.form.get('category') or '').strip())
    status = (request.form.get('status') or 'active').strip().lower()
    if status not in ('active', 'inactive', 'archived'):
        status = 'active'
    try:
        price = float(request.form.get('price', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid price.'}), 400
    try:
        stock_quantity = int(request.form.get('stock_quantity', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid stock quantity.'}), 400

    is_draft = status == 'inactive'
    user = User.query.get(user_id)
    default_cats = _seller_category_choices(user)

    if is_draft:
        if not name:
            return jsonify({'success': False, 'message': 'Product name is required for a draft.'}), 400
        if not description:
            description = ''
        if not category:
            category = default_cats[0] if default_cats else 'Other'
        price = max(0.0, price)
        stock_quantity = max(0, stock_quantity)
    else:
        if not name or not description or not category:
            return jsonify({'success': False, 'message': 'Name, description, and category are required.'}), 400
        if price < 0 or stock_quantity < 0:
            return jsonify({'success': False, 'message': 'Price and stock must be zero or greater.'}), 400

    image_url = None
    if 'image' in request.files:
        image_url = _seller_save_uploaded_image(request.files['image'])
    if not image_url:
        image_url = _seller_placeholder_image(name)

    product = Product(
        name=name,
        description=description,
        price=price,
        category=category,
        stock_quantity=stock_quantity,
        image_url=image_url,
        seller_id=user_id,
        status=status,
    )
    db.session.add(product)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Product created.',
        'product': _product_to_seller_json(product),
    })


@seller_bp.route('/api/products/<int:product_id>', methods=['GET', 'PUT', 'DELETE'])
@seller_api_required
def seller_product_detail_api(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first()
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404

    if request.method == 'GET':
        return jsonify({'success': True, 'product': _product_to_seller_json(product)})

    if request.method == 'DELETE':
        has_orders = OrderItem.query.filter_by(product_id=product_id).first() is not None
        if has_orders:
            return jsonify({
                'success': False,
                'message': 'Cannot delete a product with orders. Archive it instead.',
            }), 400
        try:
            delete_product_and_dependencies(product)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Product deleted.'})
        except Exception:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'Could not delete product. Archive it instead.',
            }), 500

    # PUT — multipart or JSON (read JSON body once)
    payload = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}

    def _field(key):
        v = request.form.get(key)
        return v if v is not None else payload.get(key)

    name = _field('name')
    if name is not None:
        name = str(name).strip()
        if name:
            product.name = name
    description = _field('description')
    if description is not None:
        product.description = str(description).strip()
    category = _field('category')
    if category is not None and str(category).strip():
        product.category = normalize_category(str(category).strip())
    price_raw = _field('price')
    if price_raw is not None:
        try:
            product.price = float(price_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid price.'}), 400
    stock_raw = _field('stock_quantity')
    if stock_raw is not None:
        try:
            product.stock_quantity = int(stock_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid stock.'}), 400
    status_raw = _field('status')
    if status_raw is not None:
        st = str(status_raw).strip().lower()
        if st in ('active', 'inactive', 'archived'):
            product.status = st

    if 'image' in request.files and request.files['image'].filename:
        new_url = _seller_save_uploaded_image(request.files['image'])
        if new_url:
            product.image_url = new_url

    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Product updated.',
        'product': _product_to_seller_json(product),
    })


@seller_bp.route('/api/products/<int:product_id>/archive', methods=['POST'])
@seller_api_required
def seller_product_archive_api(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first()
    if not product:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    product.status = 'archived'
    db.session.commit()
    return jsonify({'success': True, 'message': 'Archived.', 'product': _product_to_seller_json(product)})


@seller_bp.route('/api/products/<int:product_id>/activate', methods=['POST'])
@seller_api_required
def seller_product_activate_api(product_id):
    user_id = session['user_id']
    product = Product.query.filter_by(id=product_id, seller_id=user_id).first()
    if not product:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    product.status = 'active'
    db.session.commit()
    return jsonify({'success': True, 'message': 'Product is now active.', 'product': _product_to_seller_json(product)})


@seller_bp.route('/api/notifications')
@seller_api_required
def seller_notifications_api():
    user_id = session['user_id']
    rows = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(80).all()
    return jsonify({
        'success': True,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'is_read': n.is_read,
            'type': n.notification_type,
            'notification_type': n.notification_type,
            'created_at': isoformat_utc_z(n.created_at) if n.created_at else None,
        } for n in rows],
    })


@seller_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@seller_api_required
def seller_notification_read_api(notification_id):
    user_id = session['user_id']
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    n.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@seller_bp.route('/api/profile', methods=['GET', 'PUT'])
@seller_api_required
def seller_profile_api():
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
        if 'product_categories' in payload:
            pc = payload.get('product_categories')
            if isinstance(pc, list):
                user.product_categories = json.dumps(pc)
            elif isinstance(pc, str):
                user.product_categories = pc
        db.session.commit()
        session['user_name'] = f'{user.first_name} {user.last_name}'
        return jsonify({'success': True, 'message': 'Profile updated.', 'profile': _seller_profile_payload(user)})
    return jsonify(_seller_profile_payload(user))


@seller_bp.route('/api/profile/picture', methods=['POST', 'DELETE'])
@seller_api_required
def seller_profile_picture_api():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    if request.method == 'DELETE':
        user.profile_picture = None
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Profile picture removed.',
            'profile': _seller_profile_payload(user),
        })

    if 'profile_picture' not in request.files:
        return jsonify({'success': False, 'message': 'Missing file field profile_picture.'}), 400
    file = request.files['profile_picture']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file selected.'}), 400

    filename = secure_filename(file.filename)
    if not filename or not _allowed_seller_profile_image(filename):
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
        'profile': _seller_profile_payload(user),
    })


@seller_bp.route('/api/chat/rooms', methods=['GET'])
@seller_api_required
def seller_chat_rooms_api():
    user_id = session['user_id']
    rooms = ChatRoom.query.filter(
        ChatRoom.seller_id == user_id,
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
            'peer_name': _peer_label_seller_room(room),
            'peer_role': _seller_peer_role(room),
            'order_id': room.order_id,
            'last_message_preview': (
                (last.message[:120] + '…') if last and len(last.message) > 120 else (last.message if last else '')
            ),
            'updated_at': isoformat_utc_z(room.updated_at) if room.updated_at else None,
            'unread_count': unread,
        })
    return jsonify({'success': True, 'rooms': payload})


@seller_bp.route('/api/chat/<int:room_id>/messages', methods=['GET', 'POST'])
@seller_api_required
def seller_chat_messages_api(room_id):
    user_id = session['user_id']
    room = ChatRoom.query.filter_by(id=room_id, seller_id=user_id).first()
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
        'peer_name': _peer_label_seller_room(room),
        'peer_role': _seller_peer_role(room),
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


@seller_bp.route('/sales-report/pdf')
@login_required
def sales_report_pdf():
    user_id = session['user_id']
    period = request.args.get('period', 'month')
    if period not in ['day', 'week', 'month', 'year']:
        period = 'month'

    seller = User.query.get(user_id)
    analytics = _get_sales_analytics_data(user_id, period)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Seller Sales Analytics Report")
    y -= 24
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Seller: {seller.first_name} {seller.last_name} ({seller.email})")
    y -= 16
    pdf.drawString(40, y, f"Period: {period.title()} ({analytics['start_date']} to {analytics['end_date']})")
    y -= 16
    pdf.drawString(40, y, f"Generated: {format_ph_datetime(get_ph_time(), '%Y-%m-%d %H:%M:%S')}")

    y -= 28
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, y, f"Total Sales: PHP {analytics['total_sales']:.2f}")
    y -= 18
    pdf.drawString(40, y, f"Total Commission: PHP {analytics['total_commission']:.2f}")

    y -= 26
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
    filename = f"sales_report_{period}_{get_ph_time().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@seller_bp.route('/profile', methods=['GET', 'POST'])
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
        return redirect(url_for('seller.profile'))
    
    return render_template('seller/profile.html', user=user)

@seller_bp.route('/notifications')
@login_required
def notifications():
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    return render_template('seller/notifications.html', notifications=notifications)


@seller_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    notification.is_read = True
    db.session.commit()
    flash('Notification marked as read.', 'success')
    return redirect(url_for('seller.notifications'))


@seller_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('seller.notifications'))


@seller_bp.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    flash('Notification deleted.', 'success')
    return redirect(url_for('seller.notifications'))


@seller_bp.route('/notifications/delete-all', methods=['POST'])
@login_required
def delete_all_notifications():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash('All notifications deleted.', 'success')
    return redirect(url_for('seller.notifications'))

@seller_bp.route('/chat')
@login_required
def chat():
    user_id = session['user_id']
    
    # Get chat rooms where user is seller (both seller_rider and buyer_seller)
    chat_rooms = ChatRoom.query.filter(
        ChatRoom.seller_id == user_id,
        ChatRoom.is_active == True
    ).order_by(ChatRoom.updated_at.desc()).all()
    
    return render_template('seller/chat.html', chat_rooms=chat_rooms)

@seller_bp.route('/chat/<int:chat_room_id>')
@login_required
def chat_room(chat_room_id):
    user_id = session['user_id']
    
    # Get chat room
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, seller_id=user_id).first_or_404()
    
    # Get messages
    messages = ChatMessage.query.filter_by(chat_room_id=chat_room_id).order_by(ChatMessage.created_at.asc()).all()
    
    # Mark messages as read
    for message in messages:
        if message.sender_id != user_id:
            message.is_read = True
    db.session.commit()
    
    return render_template('seller/chat_room.html', chat_room=chat_room, messages=messages)

@seller_bp.route('/chat/<int:chat_room_id>/send-message', methods=['POST'])
@login_required
def send_message(chat_room_id):
    user_id = session['user_id']
    message_text = request.form.get('message')
    
    if not message_text:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('seller.chat_room', chat_room_id=chat_room_id))
    
    # Verify user has access to this chat room
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, seller_id=user_id).first_or_404()
    
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
    
    return redirect(url_for('seller.chat_room', chat_room_id=chat_room_id))
