from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from database import (
    db,
    User,
    Product,
    Order,
    OrderItem,
    Review,
    Notification,
    Cart,
    CartItem,
    ChatRoom,
    ChatMessage,
    Wishlist,
    Delivery,
    Advertisement,
    SellerAdvertisement,
    apply_seller_ad_to_buyer_cart_items,
    apply_admin_promo_to_buyer_cart,
    reconcile_buyer_cart_promos_from_session,
    find_claimable_admin_advertisement_by_promo_code,
    mobile_cart_snapshot_json,
    seller_display_name,
    order_pickup_shop_labels,
    effective_order_status,
    filter_orders_by_tab,
)
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func
from timezone_utils import (
    is_advertisement_visible,
    is_admin_site_advertisement_visible,
    is_admin_site_advertisement_claimable,
    isoformat_utc_z,
)
import secrets
import os

from mobile_session import signed_session_cookie_pair

buyer_bp = Blueprint('buyer', __name__)


def _filter_buyer_orders_query(query, status_filter):
    """Map My Orders tabs; delivered includes delivery.status=delivered."""
    sf = (status_filter or 'all').strip().lower()
    allowed = (
        'all',
        'pending',
        'preparing',
        'shipped',
        'delivered',
        'cancelled',
        'refunded',
    )
    if sf not in allowed:
        return query
    return filter_orders_by_tab(query, sf)


def _notify_seller_product_review(product, buyer_user, rating, was_update):
    """Alerts seller when a buyer submits or updates a review (web + mobile)."""
    if not product or not product.seller_id:
        return
    label = 'A buyer'
    if buyer_user:
        label = (
            f'{buyer_user.first_name or ""} {buyer_user.last_name or ""}'.strip()
            or buyer_user.email
            or label
        )
    title = 'Review updated on your listing' if was_update else 'New customer review'
    msg = f'{label} rated "{product.name}" {rating}/5 stars on your store.'
    db.session.add(
        Notification(
            user_id=product.seller_id,
            title=title,
            message=msg,
            notification_type='product_review',
        )
    )


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'buyer':
            flash('Please login as a buyer to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def buyer_api_required(f):
    """JSON 401 for mobile / API clients (no HTML redirect)."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'buyer':
            return jsonify({'success': False, 'message': 'Please login as a buyer.'}), 401
        return f(*args, **kwargs)
    return decorated_function


def _order_timeline_entries(order, delivery):
    """Build delivery timeline for mobile track screen (order + delivery state)."""
    def fmt(dt):
        return isoformat_utc_z(dt)

    dstatus = delivery.status if delivery else None
    ostatus = order.status

    # Completed flags aligned with website order / delivery flow
    placed_done = True
    seller_done = ostatus in ('confirmed', 'preparing', 'shipped', 'delivered')
    pickup_done = dstatus in ('picked_up', 'in_transit', 'delivered')
    transit_done = (
        ostatus in ('shipped', 'delivered')
        or dstatus in ('in_transit', 'delivered')
    )
    out_done = dstatus in ('in_transit', 'delivered') or ostatus == 'delivered'
    delivered_done = ostatus == 'delivered'

    entries = [
        {
            'id': 'placed',
            'title': 'Order Placed',
            'completed': placed_done,
            'timestamp': fmt(order.created_at),
        },
        {
            'id': 'seller',
            'title': 'Seller Approved',
            'completed': seller_done,
            'timestamp': fmt(order.updated_at if seller_done else None),
        },
        {
            'id': 'pickup',
            'title': 'Rider Picked Up',
            'completed': pickup_done,
            'timestamp': fmt(delivery.updated_at if pickup_done and delivery else None),
        },
        {
            'id': 'transit',
            'title': 'In Transit',
            'completed': transit_done,
            'timestamp': fmt(delivery.updated_at if transit_done and delivery else None),
        },
        {
            'id': 'out',
            'title': 'Out for Delivery',
            'completed': out_done,
            'timestamp': fmt(delivery.updated_at if out_done and delivery else None),
        },
        {
            'id': 'delivered',
            'title': 'Delivered',
            'completed': delivered_done,
            'timestamp': fmt(order.updated_at if delivered_done else None),
        },
    ]
    return entries


def _delivery_status_label(status):
    if not status:
        return 'Awaiting rider assignment'
    labels = {
        'pending': 'Waiting for a rider',
        'assigned': 'Rider assigned',
        'picked_up': 'Picked up from seller',
        'in_transit': 'On the way to you',
        'delivered': 'Delivered',
    }
    return labels.get(status, status.replace('_', ' ').title())


def _rider_public_dict(delivery):
    if not delivery or not delivery.rider_id:
        return None
    rider = User.query.get(delivery.rider_id)
    if not rider:
        return None
    return {
        'id': rider.id,
        'name': f'{rider.first_name or ""} {rider.last_name or ""}'.strip() or 'Rider',
        'phone': rider.contact_number or '',
    }


def _normalize_pod_image_url(raw):
    """Return path relative to Flask /static for local files, or full http(s) URL."""
    if not raw:
        return ''
    u = str(raw).strip().replace('\\', '/')
    if not u:
        return ''
    low = u.lower()
    if low.startswith('http://') or low.startswith('https://'):
        return u
    if u.startswith('static/'):
        u = u[len('static/') :]
    return u.lstrip('/')


def _proof_of_delivery_dict(delivery):
    if not delivery:
        return None
    image_url = _normalize_pod_image_url(getattr(delivery, 'pod_image_url', None) or '')
    remarks = (getattr(delivery, 'pod_remarks', None) or '').strip()
    if not image_url and not remarks:
        return None
    return {
        'image_url': image_url,
        'remarks': remarks,
    }


def _admin_store_offer_dict(ad):
    if not ad:
        return None
    return {
        'id': ad.id,
        'title': ad.title,
        'description': (ad.description or '')[:2000],
        'image_url': ad.image_url or '',
        'discount_percentage': int(ad.discount_percentage or 0),
        'expires_at': isoformat_utc_z(ad.expires_at) if ad.expires_at else None,
        'promo_code': (ad.promo_code or '').strip(),
    }


def _seller_deal_dict(ad):
    if not ad:
        return None
    p = ad.product
    return {
        'id': ad.id,
        'title': ad.title,
        'description': (ad.description or '')[:2000],
        'image_url': ad.image_url or '',
        'discount_percentage': int(ad.discount_percentage or 0),
        'original_price': float(ad.original_price or 0),
        'discounted_price': float(ad.discounted_price or 0),
        'product_id': ad.product_id,
        'product_name': p.name if p else '',
        'product_image_url': (p.image_url or '') if p else '',
    }


def _visible_admin_offers_for_store():
    return [
        a
        for a in Advertisement.query.filter_by(is_active=True).all()
        if is_admin_site_advertisement_visible(a)
    ]


def _visible_seller_deals_for_store(limit=30):
    candidates = (
        SellerAdvertisement.query.join(
            Product, SellerAdvertisement.product_id == Product.id
        )
        .filter(
            SellerAdvertisement.is_active == True,  # noqa: E712
            SellerAdvertisement.is_approved == True,  # noqa: E712
            Product.status == 'active',
        )
        .order_by(SellerAdvertisement.created_at.desc())
        .limit(60)
        .all()
    )
    visible = [a for a in candidates if is_advertisement_visible(a)['visible']]
    return visible[:limit]


def _session_active_admin_offer():
    if not session.get('admin_store_promo_unlocked'):
        return None
    ap = session.get('active_admin_promo') or {}
    aid = ap.get('admin_ad_id')
    if not aid:
        return None
    aad = Advertisement.query.filter_by(id=aid, is_active=True).first()
    if aad and is_admin_site_advertisement_claimable(aad):
        return aad
    return None


def _session_active_seller_deal():
    ac = session.get('active_discount') or {}
    ad_id = ac.get('ad_id')
    if not ad_id:
        return None
    sad = SellerAdvertisement.query.filter_by(
        id=ad_id, is_active=True, is_approved=True
    ).first()
    if sad and is_advertisement_visible(sad)['visible']:
        return sad
    return None


@buyer_bp.route('/api/promotions', methods=['GET'])
@buyer_api_required
def buyer_promotions_api():
    """Live admin store offers + seller product deals; mirrors web home / buyer promos page."""
    admin_raw = _visible_admin_offers_for_store()
    seller_raw = _visible_seller_deals_for_store(30)
    a_admin = _session_active_admin_offer()
    a_seller = _session_active_seller_deal()
    return jsonify({
        'success': True,
        'admin_offers': [_admin_store_offer_dict(x) for x in admin_raw],
        'seller_deals': [_seller_deal_dict(x) for x in seller_raw],
        'session': {
            'active_admin_offer': _admin_store_offer_dict(a_admin),
            'active_seller_deal': _seller_deal_dict(a_seller),
        },
    })


@buyer_bp.route('/api/promotions/claim-store-offer', methods=['POST'])
@buyer_api_required
def buyer_promotions_claim_store_api():
    """Store-wide admin % applies only after entering the promo code on the cart."""
    payload = request.get_json(silent=True) or {}
    raw_id = payload.get('admin_ad_id')
    try:
        admin_ad_id = int(raw_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'admin_ad_id is required.'}), 400

    ad = Advertisement.query.filter_by(id=admin_ad_id, is_active=True).first()
    if not ad or not is_admin_site_advertisement_claimable(ad):
        return jsonify({'success': False, 'message': 'This offer is not available or has expired.'}), 400

    code = getattr(ad, 'promo_code', None) or None
    msg = (
        'Enter this store offer\'s promo code on the Shopping Cart screen to apply the discount.'
    )
    return jsonify({
        'success': False,
        'message': msg,
        'promo_code': code,
        'session_cookie': signed_session_cookie_pair(),
        'session': {
            'active_admin_offer': None,
            'active_seller_deal': _seller_deal_dict(_session_active_seller_deal()),
        },
    }), 200


@buyer_bp.route('/api/promotions/activate-seller-deal', methods=['POST'])
@buyer_api_required
def buyer_promotions_activate_seller_api():
    """Same as web seller ad click — session discount + cart lines for that SKU updated."""
    payload = request.get_json(silent=True) or {}
    raw_id = payload.get('seller_ad_id')
    try:
        seller_ad_id = int(raw_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'seller_ad_id is required.'}), 400

    advertisement = SellerAdvertisement.query.filter_by(
        id=seller_ad_id, is_active=True, is_approved=True
    ).first()
    if not advertisement:
        return jsonify({'success': False, 'message': 'Deal not found or inactive.'}), 404
    if not is_advertisement_visible(advertisement)['visible']:
        return jsonify({'success': False, 'message': 'This deal is not available yet or has expired.'}), 400

    session['active_discount'] = {
        'ad_id': advertisement.id,
        'discount_percentage': advertisement.discount_percentage,
        'discounted_price': float(advertisement.discounted_price),
        'expires_at': isoformat_utc_z(advertisement.expires_at) if advertisement.expires_at else None,
    }

    uid = session['user_id']
    apply_seller_ad_to_buyer_cart_items(uid, advertisement)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Seller deal saved to your session and applied to matching cart lines.',
        'product_id': advertisement.product_id,
        'session_cookie': signed_session_cookie_pair(),
        'session': {
            'active_admin_offer': _admin_store_offer_dict(_session_active_admin_offer()),
            'active_seller_deal': _seller_deal_dict(_session_active_seller_deal()),
        },
    })


@buyer_bp.route('/api/cart/apply-promo-code', methods=['POST'])
@buyer_api_required
def buyer_apply_store_promo_code_api():
    """Apply admin store promo by code (sets session unlock + eligible cart lines)."""
    payload = request.get_json(silent=True) or {}
    code = (payload.get('promo_code') or payload.get('code') or '').strip()
    if not code:
        code = (request.form.get('promo_code') or request.form.get('code') or '').strip()
    ad = find_claimable_admin_advertisement_by_promo_code(code)
    if not ad:
        return jsonify({
            'success': False,
            'message': (
                'Invalid or expired code, or no Promo code is set on that store offer. '
                'In Admin → Advertisements, edit the banner and set the Promo code field '
                '(saved uppercase). Try SUMMER25 or FITNESS25 if you use sample seed data.'
            ),
        }), 400

    session['admin_store_promo_unlocked'] = True
    session['active_admin_promo'] = {'admin_ad_id': ad.id}
    session.modified = True
    uid = session['user_id']
    apply_admin_promo_to_buyer_cart(uid, ad)
    db.session.commit()

    label = ad.promo_code or 'STORE'
    snap = mobile_cart_snapshot_json(uid)
    pct = int(ad.discount_percentage or 0)
    return jsonify({
        'success': True,
        'message': f'Store promo {label} applied ({ad.discount_percentage}% off eligible cart lines).',
        'session_cookie': signed_session_cookie_pair(),
        'store_promo_percent': pct,
        **snap,
    })


@buyer_bp.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Get recent orders
    recent_orders = Order.query.filter_by(buyer_id=user_id).order_by(Order.created_at.desc()).limit(5).all()
    
    # Get cart count
    cart = Cart.query.filter_by(user_id=user_id).first()
    cart_count = CartItem.query.filter_by(cart_id=cart.id).count() if cart else 0
    
    # Get unread notifications
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    
    return render_template('buyer/dashboard.html',
                         user=user,
                         recent_orders=recent_orders,
                         cart_count=cart_count,
                         unread_notifications=unread_notifications)

@buyer_bp.route('/orders')
@login_required
def orders():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')
    
    query = Order.query.filter_by(buyer_id=user_id)
    query = _filter_buyer_orders_query(query, status_filter)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    return render_template('buyer/orders.html', orders=orders, current_status=status_filter)

@buyer_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, buyer_id=user_id).first_or_404()
    delivery = order.delivery
    timeline = _order_timeline_entries(order, delivery)

    return render_template(
        'buyer/order_detail.html',
        order=order,
        delivery=delivery,
        rider_user=User.query.get(delivery.rider_id) if delivery and delivery.rider_id else None,
        delivery_status_label=_delivery_status_label(delivery.status if delivery else None),
        timeline=timeline,
        proof_of_delivery=_proof_of_delivery_dict(delivery),
        pickup_shops_summary=order_pickup_shop_labels(order),
    )

@buyer_bp.route('/place-order', methods=['POST'])
@login_required
def place_order():
    user_id = session['user_id']
    payment_method = request.form.get('payment_method', 'cash_on_delivery')

    if session.get('user_type') == 'buyer':
        reconcile_buyer_cart_promos_from_session(user_id, session)
        db.session.commit()

    # Get user's cart
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart or not cart.items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('main.cart'))

    selected_cart_item_ids = set(request.form.getlist('selected_cart_items'))
    if not selected_cart_item_ids:
        flash('Please select at least one cart item to checkout.', 'warning')
        return redirect(url_for('main.cart'))

    selected_items = [item for item in cart.items if str(item.id) in selected_cart_item_ids]
    if not selected_items:
        flash('Selected cart items are invalid. Please try again.', 'error')
        return redirect(url_for('main.cart'))
    
    # Create order
    order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000):03d}"
    # Calculate total using discounted prices
    total_amount = sum((item.discounted_price or item.product.price) * item.quantity for item in selected_items)
    
    # Get user for shipping address
    user = User.query.get(user_id)
    shipping_address = f"{user.address_barangay}, {user.address_city}, {user.address_province}, {user.address_region}"
    
    order = Order(
        order_number=order_number,
        buyer_id=user_id,
        total_amount=total_amount,
        payment_method=payment_method,
        shipping_address=shipping_address
    )
    
    db.session.add(order)
    db.session.flush()  # Get order ID
    
    # Create order items and update product stock
    for cart_item in selected_items:
        if cart_item.product.stock_quantity <= 0:
            flash(f'"{cart_item.product.name}" is now out of stock. Please update your cart.', 'error')
            return redirect(url_for('main.cart'))
        if cart_item.quantity > cart_item.product.stock_quantity:
            flash(
                f'Only {cart_item.product.stock_quantity} stock left for "{cart_item.product.name}". '
                'Please update your cart quantity.',
                'error'
            )
            return redirect(url_for('main.cart'))

        # Use discounted price if available, otherwise use original price
        final_price = cart_item.discounted_price or cart_item.product.price
        
        order_item = OrderItem(
            order_id=order.id,
            product_id=cart_item.product_id,
            quantity=cart_item.quantity,
            price=final_price,
            original_price=cart_item.product.price,
            discount_percentage=cart_item.discount_percentage,
            advertisement_id=cart_item.advertisement_id
        )
        db.session.add(order_item)
        
        # Update product stock
        cart_item.product.stock_quantity -= cart_item.quantity
    
    # Remove only selected items from cart.
    for cart_item in selected_items:
        db.session.delete(cart_item)

    # Delete cart container only when empty to avoid stale/duplicate delete warnings.
    remaining_items = [item for item in cart.items if str(item.id) not in selected_cart_item_ids]
    if not remaining_items:
        db.session.delete(cart)
    
    db.session.commit()
    
    # Create delivery record
    from database import Delivery
    delivery = Delivery(
        order_id=order.id,
        status='pending',
        pickup_address=shipping_address,  # For now, using buyer address as pickup
        delivery_address=shipping_address,
        commission_amount=Decimal(str(total_amount)) * Decimal('0.05')  # 5% commission for rider
    )
    db.session.add(delivery)
    
    # Notify seller and create buyer-seller chat rooms
    seller_ids = set(item.product.seller_id for item in order.items)
    for seller_id in seller_ids:
        notification = Notification(
            user_id=seller_id,
            title='New Order Received',
            message=f'You have received a new order: {order_number}',
            notification_type='order'
        )
        db.session.add(notification)
        
        # Create buyer-seller chat room
        chat_room = ChatRoom(
            room_name=f'Order {order_number} - Buyer & Seller',
            room_type='buyer_seller',
            buyer_id=user_id,
            seller_id=seller_id,
            order_id=order.id
        )
        db.session.add(chat_room)
    
    # Notify riders about new delivery
    riders = User.query.filter_by(user_type='rider', is_approved=True).all()
    for rider in riders:
        notification = Notification(
            user_id=rider.id,
            title='New Delivery Available',
            message=f'New delivery available for order: {order_number}',
            notification_type='delivery_available'
        )
        db.session.add(notification)
    
    db.session.commit()
    
    flash('Order placed successfully!', 'success')
    return redirect(url_for('buyer.order_detail', order_id=order.id))


@buyer_bp.route('/api/orders')
@buyer_api_required
def orders_api():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')

    query = Order.query.filter_by(buyer_id=user_id)
    query = _filter_buyer_orders_query(query, status_filter)
    orders = query.order_by(Order.created_at.desc()).all()

    payload = []
    for order in orders:
        first_item = order.items[0] if order.items else None
        primary_product_name = first_item.product.name if first_item else 'Order'
        primary_product_id = first_item.product_id if first_item else None
        seller_display_name = 'Seller'
        if first_item:
            seller = User.query.get(first_item.product.seller_id)
            if seller:
                seller_display_name = (
                    f'{seller.first_name or ""} {seller.last_name or ""}'.strip()
                    or seller.email
                    or 'Seller'
                )
        delivery = order.delivery
        delivery_status = delivery.status if delivery else None
        rider_name = None
        rider_phone = None
        if delivery and delivery.rider_id:
            rider = User.query.get(delivery.rider_id)
            if rider:
                rider_name = f'{rider.first_name or ""} {rider.last_name or ""}'.strip() or 'Rider'
                rider_phone = rider.contact_number or ''
        payload.append({
            'id': order.id,
            'order_number': order.order_number,
            'total_amount': float(order.total_amount),
            'status': effective_order_status(order),
            'payment_method': order.payment_method,
            'created_at': isoformat_utc_z(order.created_at),
            'item_count': len(order.items),
            'primary_product_name': primary_product_name,
            'primary_product_id': primary_product_id,
            'seller_display_name': seller_display_name,
            'delivery_status': delivery_status,
            'rider_name': rider_name,
            'rider_phone': rider_phone,
        })

    return jsonify({'orders': payload})


@buyer_bp.route('/api/orders/<int:order_id>')
@buyer_api_required
def order_detail_api(order_id):
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, buyer_id=user_id).first_or_404()
    delivery = order.delivery
    rider = _rider_public_dict(delivery)

    items = []
    for item in order.items:
        prod = item.product
        items.append({
            'product_id': item.product_id,
            'product_name': prod.name if prod else '',
            'shop_name': seller_display_name(prod.seller if prod else None),
            'seller_id': prod.seller_id if prod else None,
            'quantity': item.quantity,
            'price': float(item.price),
            'original_price': float(item.original_price or item.price),
            'discount_percentage': item.discount_percentage,
            'line_total': float(item.price) * item.quantity,
        })

    return jsonify({
        'order': {
            'id': order.id,
            'order_number': order.order_number,
            'total_amount': float(order.total_amount),
            'status': effective_order_status(order),
            'payment_method': order.payment_method,
            'shipping_address': order.shipping_address,
            'created_at': isoformat_utc_z(order.created_at),
            'updated_at': isoformat_utc_z(order.updated_at) if order.updated_at else None,
            'pickup_shop': order_pickup_shop_labels(order),
            'items': items,
            'delivery_status': delivery.status if delivery else None,
            'delivery_status_label': _delivery_status_label(delivery.status if delivery else None),
            'delivery_updated_at': isoformat_utc_z(delivery.updated_at) if delivery and delivery.updated_at else None,
            'rider': rider,
            'timeline': _order_timeline_entries(order, delivery),
            'proof_of_delivery': _proof_of_delivery_dict(delivery),
        }
    })


@buyer_bp.route('/api/orders/<int:order_id>/track', methods=['GET'])
@buyer_api_required
def order_track_api(order_id):
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, buyer_id=user_id).first()
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404

    delivery = order.delivery
    rider_payload = None
    if delivery and delivery.rider_id:
        rider = User.query.get(delivery.rider_id)
        if rider:
            rider_payload = {
                'name': f'{rider.first_name or ""} {rider.last_name or ""}'.strip() or 'Rider',
                'phone': rider.contact_number or '',
            }

    first_item = order.items[0] if order.items else None
    product_label = first_item.product.name if first_item else 'Order'

    track_items = []
    for item in order.items:
        prod = item.product
        track_items.append({
            'product_name': prod.name if prod else '',
            'quantity': int(item.quantity or 0),
            'shop_name': seller_display_name(prod.seller if prod else None),
        })

    return jsonify({
        'success': True,
        'order_number': order.order_number,
        'order_status': order.status,
        'product_name': product_label,
        'pickup_shop': order_pickup_shop_labels(order),
        'items': track_items,
        'delivery_status': delivery.status if delivery else None,
        'rider': rider_payload,
        'timeline': _order_timeline_entries(order, delivery),
        'proof_of_delivery': _proof_of_delivery_dict(delivery),
    })


def _buyer_profile_payload(user):
    """Shared dict for GET profile / mobile."""
    full_name = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    address_line = (
        f'{user.address_barangay}, {user.address_city}, {user.address_province}, {user.address_region}'
    ).strip(', ')
    uid = user.id
    orders_count = Order.query.filter(
        Order.buyer_id == uid,
        Order.status != 'cancelled',
    ).count()
    reviews_count = Review.query.filter_by(user_id=uid).count()
    total_spent_q = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
        Order.buyer_id == uid,
        Order.status.in_(('pending', 'confirmed', 'preparing', 'shipped', 'delivered')),
    ).scalar()
    total_spent = float(total_spent_q or 0)
    wishlist_count = Wishlist.query.filter_by(user_id=uid).count()
    unread_notifications = Notification.query.filter_by(user_id=uid, is_read=False).count()
    rooms = ChatRoom.query.filter(
        ChatRoom.buyer_id == uid,
        ChatRoom.is_active == True,  # noqa: E712
    ).all()
    messages_unread = 0
    for room in rooms:
        messages_unread += ChatMessage.query.filter(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.sender_id != uid,
            ChatMessage.is_read == False,  # noqa: E712
        ).count()
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
        'orders_count': orders_count,
        'reviews_count': reviews_count,
        'total_spent': total_spent,
        'wishlist_count': wishlist_count,
        'unread_notifications': unread_notifications,
        'messages_unread': messages_unread,
        'profile_picture': user.profile_picture or '',
    }


def _allowed_buyer_profile_image(filename):
    ext = os.path.splitext((filename or '').lower())[1]
    return ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')


@buyer_bp.route('/api/profile/picture', methods=['POST', 'DELETE'])
@buyer_api_required
def buyer_profile_picture_api():
    """Multipart upload (field profile_picture) or remove photo — matches web static/uploads/profiles."""
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    if request.method == 'DELETE':
        user.profile_picture = None
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Profile picture removed.',
            'profile': _buyer_profile_payload(user),
        })

    if 'profile_picture' not in request.files:
        return jsonify({'success': False, 'message': 'Missing file field profile_picture.'}), 400
    file = request.files['profile_picture']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file selected.'}), 400

    filename = secure_filename(file.filename)
    if not filename or not _allowed_buyer_profile_image(filename):
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
        'profile': _buyer_profile_payload(user),
    })


@buyer_bp.route('/api/profile', methods=['GET', 'PUT'])
@buyer_api_required
def buyer_profile_api():
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
        db.session.commit()
        session['user_name'] = f'{user.first_name} {user.last_name}'
        return jsonify({'success': True, 'message': 'Profile updated.', 'profile': _buyer_profile_payload(user)})
    return jsonify(_buyer_profile_payload(user))


@buyer_bp.route('/api/notifications', methods=['GET'])
@buyer_api_required
def buyer_notifications_api():
    user_id = session['user_id']
    items = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(100).all()
    return jsonify({
        'success': True,
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'notification_type': n.notification_type,
                'created_at': isoformat_utc_z(n.created_at) if n.created_at else None,
            }
            for n in items
        ],
    })


@buyer_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@buyer_api_required
def buyer_notification_read_api(notification_id):
    user_id = session['user_id']
    n = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not n:
        return jsonify({'success': False, 'message': 'Not found.'}), 404
    n.is_read = True
    db.session.commit()
    return jsonify({'success': True})


def _product_json_mobile(p):
    avg = db.session.query(func.avg(Review.rating)).filter_by(product_id=p.id).scalar() or 0
    rc = Review.query.filter_by(product_id=p.id).count()
    return {
        'id': p.id,
        'name': p.name,
        'description': p.description or '',
        'price': float(p.price),
        'category': p.category,
        'stock_quantity': p.stock_quantity,
        'image_url': p.image_url,
        'created_at': isoformat_utc_z(p.created_at) if p.created_at else None,
        'avg_rating': round(float(avg), 1) if avg else 0.0,
        'review_count': int(rc),
    }


@buyer_bp.route('/api/wishlist', methods=['GET'])
@buyer_api_required
def buyer_wishlist_list_api():
    user_id = session['user_id']
    items = db.session.query(Product).join(Wishlist).filter(Wishlist.user_id == user_id).all()
    return jsonify({'success': True, 'products': [_product_json_mobile(p) for p in items]})


@buyer_bp.route('/api/wishlist/add', methods=['POST'])
@buyer_api_required
def buyer_wishlist_add_api():
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    product_id = payload.get('product_id')
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Product ID is required.'}), 400
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404
    if Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first():
        return jsonify({'success': False, 'message': 'Product already in wishlist.'}), 400
    db.session.add(Wishlist(user_id=user_id, product_id=product_id))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Added to wishlist.'})


@buyer_bp.route('/api/wishlist/remove', methods=['POST'])
@buyer_api_required
def buyer_wishlist_remove_api():
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    product_id = payload.get('product_id')
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Product ID is required.'}), 400
    row = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Removed from wishlist.'})
    return jsonify({'success': False, 'message': 'Product not in wishlist.'}), 400


@buyer_bp.route('/api/wishlist/check', methods=['GET', 'POST'])
@buyer_api_required
def buyer_wishlist_check_api():
    """Whether a single product is on the buyer wishlist (mobile product cards / detail)."""
    user_id = session['user_id']
    if request.method == 'GET':
        product_id = request.args.get('product_id')
    else:
        payload = request.get_json(silent=True) or {}
        product_id = payload.get('product_id')
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Product ID is required.'}), 400
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404
    row = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    return jsonify({'success': True, 'is_in_wishlist': row is not None})


def _peer_label_chat_room(room):
    if room.seller_id:
        u = User.query.get(room.seller_id)
        if u:
            return (f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email or 'Seller')
    if room.rider_id:
        u = User.query.get(room.rider_id)
        if u:
            return (f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email or 'Rider')
    return room.room_name or 'Chat'


@buyer_bp.route('/api/chat/rooms', methods=['GET'])
@buyer_api_required
def buyer_chat_rooms_api():
    user_id = session['user_id']
    rooms = ChatRoom.query.filter(
        ChatRoom.buyer_id == user_id,
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
            'peer_name': _peer_label_chat_room(room),
            'order_id': room.order_id,
            'last_message_preview': (last.message[:120] + '…') if last and len(last.message) > 120 else (last.message if last else ''),
            'updated_at': isoformat_utc_z(room.updated_at) if room.updated_at else None,
            'unread_count': unread,
        })
    return jsonify({'success': True, 'rooms': payload})


@buyer_bp.route('/api/chat/<int:room_id>/messages', methods=['GET'])
@buyer_api_required
def buyer_chat_messages_api(room_id):
    user_id = session['user_id']
    room = ChatRoom.query.filter_by(id=room_id, buyer_id=user_id).first()
    if not room:
        return jsonify({'success': False, 'message': 'Chat not found.'}), 404
    messages = ChatMessage.query.filter_by(chat_room_id=room_id).order_by(ChatMessage.created_at.asc()).all()
    for m in messages:
        if m.sender_id != user_id:
            m.is_read = True
    db.session.commit()
    return jsonify({
        'success': True,
        'peer_name': _peer_label_chat_room(room),
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


@buyer_bp.route('/api/chat/<int:room_id>/messages', methods=['POST'])
@buyer_api_required
def buyer_chat_send_api(room_id):
    user_id = session['user_id']
    room = ChatRoom.query.filter_by(id=room_id, buyer_id=user_id).first()
    if not room:
        return jsonify({'success': False, 'message': 'Chat not found.'}), 404
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


@buyer_bp.route('/api/place-order', methods=['POST'])
@buyer_api_required
def place_order_api():
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    payment_method = payload.get('payment_method', 'cash_on_delivery')
    selected_cart_item_ids = set(str(item_id) for item_id in payload.get('selected_cart_items', []))

    if session.get('user_type') == 'buyer':
        reconcile_buyer_cart_promos_from_session(user_id, session)
        db.session.commit()

    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart or not cart.items:
        return jsonify({'success': False, 'message': 'Your cart is empty.'}), 400
    if not selected_cart_item_ids:
        return jsonify({'success': False, 'message': 'Please select at least one cart item to checkout.'}), 400

    selected_items = [item for item in cart.items if str(item.id) in selected_cart_item_ids]
    if not selected_items:
        return jsonify({'success': False, 'message': 'Selected cart items are invalid.'}), 400

    order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000):03d}"
    total_amount = sum((item.discounted_price or item.product.price) * item.quantity for item in selected_items)
    user = User.query.get(user_id)
    shipping_address = f"{user.address_barangay}, {user.address_city}, {user.address_province}, {user.address_region}"

    order = Order(
        order_number=order_number,
        buyer_id=user_id,
        total_amount=total_amount,
        payment_method=payment_method,
        shipping_address=shipping_address
    )
    db.session.add(order)
    db.session.flush()

    for cart_item in selected_items:
        if cart_item.product.stock_quantity <= 0:
            return jsonify({'success': False, 'message': f'"{cart_item.product.name}" is now out of stock.'}), 400
        if cart_item.quantity > cart_item.product.stock_quantity:
            return jsonify({'success': False, 'message': f'Only {cart_item.product.stock_quantity} stock left for "{cart_item.product.name}".'}), 400

        final_price = cart_item.discounted_price or cart_item.product.price
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=cart_item.product_id,
            quantity=cart_item.quantity,
            price=final_price,
            original_price=cart_item.product.price,
            discount_percentage=cart_item.discount_percentage,
            advertisement_id=cart_item.advertisement_id
        ))
        cart_item.product.stock_quantity -= cart_item.quantity

    for cart_item in selected_items:
        db.session.delete(cart_item)

    remaining_items = [item for item in cart.items if str(item.id) not in selected_cart_item_ids]
    if not remaining_items:
        db.session.delete(cart)

    db.session.add(Delivery(
        order_id=order.id,
        status='pending',
        pickup_address=shipping_address,
        delivery_address=shipping_address,
        commission_amount=Decimal(str(total_amount)) * Decimal('0.05')
    ))

    # Keep API checkout behavior aligned with website checkout:
    # notify sellers and riders that a new order/delivery is available.
    seller_ids = set(item.product.seller_id for item in selected_items)
    for seller_id in seller_ids:
        db.session.add(Notification(
            user_id=seller_id,
            title='New Order Received',
            message=f'You have received a new order: {order_number}',
            notification_type='order'
        ))

    riders = User.query.filter_by(user_type='rider', is_approved=True).all()
    for rider in riders:
        db.session.add(Notification(
            user_id=rider.id,
            title='New Delivery Available',
            message=f'New delivery available for order: {order_number}',
            notification_type='delivery_available'
        ))

    db.session.commit()
    return jsonify({'success': True, 'order_id': order.id, 'order_number': order.order_number})


@buyer_bp.route('/api/cancel-order', methods=['POST'])
@buyer_api_required
def cancel_order_api():
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    oid = payload.get('order_id')
    try:
        order_id = int(oid)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid order.'}), 400

    order = Order.query.filter_by(id=order_id, buyer_id=user_id).first()
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404

    if order.status not in ('pending', 'confirmed'):
        return jsonify({'success': False, 'message': 'Cannot cancel this order.'}), 400

    for item in order.items:
        item.product.stock_quantity += item.quantity

    order.status = 'cancelled'
    db.session.commit()

    seller_ids = set(item.product.seller_id for item in order.items)
    for seller_id in seller_ids:
        db.session.add(Notification(
            user_id=seller_id,
            title='Order Cancelled',
            message=f'Order {order.order_number} has been cancelled by the buyer.',
            notification_type='order_cancelled'
        ))
    db.session.commit()

    return jsonify({'success': True, 'message': 'Order cancelled successfully.'})


@buyer_bp.route('/api/review', methods=['POST'])
@buyer_api_required
def review_product_api():
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    try:
        product_id = int(payload.get('product_id', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid product.'}), 400
    try:
        rating = int(payload.get('rating', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid rating.'}), 400
    comment = (payload.get('comment') or '').strip()

    if product_id <= 0 or rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Rating must be between 1 and 5.'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404

    has_delivered = OrderItem.query.join(Order).filter(
        Order.buyer_id == user_id,
        OrderItem.product_id == product_id,
        Order.status == 'delivered'
    ).first() is not None
    if not has_delivered:
        return jsonify({
            'success': False,
            'message': 'You can only review products from delivered orders.',
        }), 400

    existing = Review.query.filter_by(user_id=user_id, product_id=product_id).first()
    was_update = existing is not None
    if existing:
        existing.rating = rating
        existing.comment = comment
    else:
        db.session.add(Review(
            user_id=user_id,
            product_id=product_id,
            rating=rating,
            comment=comment
        ))
    buyer_u = User.query.get(user_id)
    _notify_seller_product_review(product, buyer_u, rating, was_update)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Review submitted successfully.'})


@buyer_bp.route('/cancel-order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, buyer_id=user_id).first_or_404()
    
    if order.status in ['pending', 'confirmed']:
        # Restore product stock
        for item in order.items:
            item.product.stock_quantity += item.quantity
        
        order.status = 'cancelled'
        db.session.commit()
        
        # Notify seller
        seller_ids = set(item.product.seller_id for item in order.items)
        for seller_id in seller_ids:
            notification = Notification(
                user_id=seller_id,
                title='Order Cancelled',
                message=f'Order {order.order_number} has been cancelled by the buyer.',
                notification_type='order_cancelled'
            )
            db.session.add(notification)
        
        db.session.commit()
        
        flash('Order cancelled successfully.', 'success')
    else:
        flash('Cannot cancel this order.', 'error')
    
    return redirect(url_for('buyer.order_detail', order_id=order_id))

@buyer_bp.route('/request-refund/<int:order_id>', methods=['POST'])
@login_required
def request_refund(order_id):
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, buyer_id=user_id).first_or_404()
    
    if order.status == 'delivered':
        order.status = 'refunded'
        db.session.commit()
        
        # Notify admin
        admin_users = User.query.filter_by(user_type='admin').all()
        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                title='Refund Request',
                message=f'Buyer {session.get("user_name")} requested refund for order {order.order_number}',
                notification_type='refund_request'
            )
            db.session.add(notification)
        
        db.session.commit()
        
        flash('Refund request submitted successfully.', 'success')
    else:
        flash('Cannot request refund for this order.', 'error')
    
    return redirect(url_for('buyer.order_detail', order_id=order_id))

@buyer_bp.route('/review/<int:product_id>', methods=['GET', 'POST'])
@login_required
def review_product(product_id):
    user_id = session['user_id']
    product = Product.query.get_or_404(product_id)
    
    # Check if user has purchased this product
    has_purchased = OrderItem.query.join(Order).filter(
        Order.buyer_id == user_id,
        OrderItem.product_id == product_id,
        Order.status == 'delivered'
    ).first() is not None
    
    if not has_purchased:
        flash('You can only review products you have purchased.', 'warning')
        return redirect(url_for('main.product_detail', product_id=product_id))
    
    if request.method == 'POST':
        rating = int(request.form['rating'])
        comment = request.form.get('comment', '')
        
        # Check if user already reviewed this product
        existing_review = Review.query.filter_by(user_id=user_id, product_id=product_id).first()
        was_update = existing_review is not None

        if existing_review:
            existing_review.rating = rating
            existing_review.comment = comment
        else:
            review = Review(
                user_id=user_id,
                product_id=product_id,
                rating=rating,
                comment=comment
            )
            db.session.add(review)

        buyer_u = User.query.get(user_id)
        _notify_seller_product_review(product, buyer_u, rating, was_update)
        db.session.commit()
        flash('Review submitted successfully!', 'success')
        return redirect(url_for('main.product_detail', product_id=product_id))
    
    # Check if user already reviewed
    existing_review = Review.query.filter_by(user_id=user_id, product_id=product_id).first()
    
    return render_template('buyer/review_product.html', 
                         product=product, 
                         existing_review=existing_review)

@buyer_bp.route('/profile', methods=['GET', 'POST'])
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
        return redirect(url_for('buyer.profile'))
    
    return render_template('buyer/profile.html', user=user)

@buyer_bp.route('/notifications')
@login_required
def notifications():
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    return render_template('buyer/notifications.html', notifications=notifications)


@buyer_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    notification.is_read = True
    db.session.commit()
    flash('Notification marked as read.', 'success')
    return redirect(url_for('buyer.notifications'))


@buyer_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('buyer.notifications'))


@buyer_bp.route('/notifications/<int:notification_id>/delete', methods=['POST'])
@login_required
def delete_notification(notification_id):
    user_id = session['user_id']
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    flash('Notification deleted.', 'success')
    return redirect(url_for('buyer.notifications'))


@buyer_bp.route('/notifications/delete-all', methods=['POST'])
@login_required
def delete_all_notifications():
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash('All notifications deleted.', 'success')
    return redirect(url_for('buyer.notifications'))

@buyer_bp.route('/wishlist')
@login_required
def wishlist():
    user_id = session['user_id']
    
    # Get user's wishlist items
    wishlist_items = db.session.query(Product).join(Wishlist).filter(
        Wishlist.user_id == user_id
    ).all()
    
    return render_template('buyer/wishlist.html', wishlist_items=wishlist_items)

@buyer_bp.route('/wishlist/add', methods=['POST'])
@login_required
def add_to_wishlist():
    user_id = session['user_id']
    product_id = request.json.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID is required'})
    
    # Check if product exists
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'})
    
    # Check if already in wishlist
    existing_wishlist = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing_wishlist:
        return jsonify({'success': False, 'message': 'Product already in wishlist'})
    
    # Add to wishlist
    wishlist_item = Wishlist(user_id=user_id, product_id=product_id)
    db.session.add(wishlist_item)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Product added to wishlist'})

@buyer_bp.route('/wishlist/remove', methods=['POST'])
@login_required
def remove_from_wishlist():
    user_id = session['user_id']
    product_id = request.json.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID is required'})
    
    # Remove from wishlist
    wishlist_item = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    if wishlist_item:
        db.session.delete(wishlist_item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Product removed from wishlist'})
    else:
        return jsonify({'success': False, 'message': 'Product not in wishlist'})

@buyer_bp.route('/wishlist/check', methods=['POST'])
@login_required
def check_wishlist():
    user_id = session['user_id']
    product_id = request.json.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID is required'})
    
    # Check if product is in wishlist
    wishlist_item = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    is_in_wishlist = wishlist_item is not None
    
    return jsonify({'success': True, 'is_in_wishlist': is_in_wishlist})

@buyer_bp.route('/chat')
@login_required
def chat():
    user_id = session['user_id']
    
    # Get chat rooms where user is buyer (both rider_buyer and buyer_seller)
    chat_rooms = ChatRoom.query.filter(
        ChatRoom.buyer_id == user_id,
        ChatRoom.is_active == True
    ).order_by(ChatRoom.updated_at.desc()).all()
    
    return render_template('buyer/chat.html', chat_rooms=chat_rooms)

@buyer_bp.route('/chat/<int:chat_room_id>')
@login_required
def chat_room(chat_room_id):
    user_id = session['user_id']
    
    # Get chat room
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, buyer_id=user_id).first_or_404()
    
    # Get messages
    messages = ChatMessage.query.filter_by(chat_room_id=chat_room_id).order_by(ChatMessage.created_at.asc()).all()
    
    # Mark messages as read
    for message in messages:
        if message.sender_id != user_id:
            message.is_read = True
    db.session.commit()
    
    return render_template('buyer/chat_room.html', chat_room=chat_room, messages=messages)

@buyer_bp.route('/chat/<int:chat_room_id>/send-message', methods=['POST'])
@login_required
def send_message(chat_room_id):
    user_id = session['user_id']
    message_text = request.form.get('message')
    
    if not message_text:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('buyer.chat_room', chat_room_id=chat_room_id))
    
    # Verify user has access to this chat room
    chat_room = ChatRoom.query.filter_by(id=chat_room_id, buyer_id=user_id).first_or_404()
    
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
    
    return redirect(url_for('buyer.chat_room', chat_room_id=chat_room_id))
