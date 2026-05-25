from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g, Response
from database import (
    db,
    User,
    Product,
    Advertisement,
    Review,
    Cart,
    CartItem,
    SellerAdvertisement,
    ChatRoom,
    ChatMessage,
    Notification,
    apply_admin_promo_to_buyer_cart,
    reconcile_buyer_cart_promos_from_session,
    find_claimable_admin_advertisement_by_promo_code,
    mobile_cart_snapshot_json,
)
from sqlalchemy import func, or_
from sqlalchemy.exc import DisconnectionError, OperationalError
from datetime import datetime
import time
from timezone_utils import (
    is_advertisement_visible,
    is_admin_site_advertisement_visible,
    is_admin_site_advertisement_claimable,
    format_ph_datetime,
    isoformat_utc_z,
)
import json
from category_utils import (
    categories_for_template,
    category_match_values,
    normalize_category,
    category_slug,
)
from media_storage import resolve_product_image_url

main_bp = Blueprint('main', __name__)


def _product_to_dict(product, external_image_url=False):
    img = product.image_url
    if img:
        img = resolve_product_image_url(img, external=external_image_url) or img
    return {
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'price': float(product.price),
        'category': product.category,
        'stock_quantity': product.stock_quantity,
        'image_url': img,
        'status': product.status,
        'seller_id': product.seller_id,
    }


def _product_to_dict_for_mobile(product, avg_rating=0.0, review_count=0):
    """JSON for mobile list: includes ratings and timestamps (matches web product cards)."""
    d = _product_to_dict(product, external_image_url=True)
    d['created_at'] = isoformat_utc_z(product.created_at) if product.created_at else None
    d['avg_rating'] = round(float(avg_rating), 1) if avg_rating else 0.0
    d['review_count'] = int(review_count)
    return d

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

@main_bp.route('/')
def home():
    update_user_activity()  # Update user activity on home page visit
    
    # Get featured products
    featured_products = Product.query.filter_by(status='active').limit(6).all()
    
    # Active admin site banners (hide past expiry)
    advertisements = [
        a
        for a in Advertisement.query.filter_by(is_active=True).all()
        if is_admin_site_advertisement_visible(a)
    ]
    
    # Seller specials: only ads for active catalog products; same PH visibility as cart / click
    candidates = (
        SellerAdvertisement.query.join(
            Product, SellerAdvertisement.product_id == Product.id
        )
        .filter(
            SellerAdvertisement.is_active == True,
            SellerAdvertisement.is_approved == True,
            Product.status == 'active',
        )
        .order_by(SellerAdvertisement.created_at.desc())
        .limit(40)
        .all()
    )
    seller_ads = [a for a in candidates if is_advertisement_visible(a)['visible']][:15]
    
    return render_template('main/home.html', 
                         featured_products=featured_products,
                         advertisements=advertisements,
                         seller_ads=seller_ads,
                         categories=categories_for_template())


@main_bp.route('/admin-offer/<int:ad_id>/claim')
def claim_admin_offer(ad_id):
    """Banner / bookmark: redirects to cart with instructions; discount uses promo code only."""
    ad = Advertisement.query.filter_by(id=ad_id, is_active=True).first()
    if not ad or not is_admin_site_advertisement_claimable(ad):
        flash('This offer is not available or has expired.', 'error')
        return redirect(url_for('main.home'))

    flash(
        'Store discounts apply when you enter the promo code on your Shopping Cart.',
        'info',
    )
    if getattr(ad, 'promo_code', None):
        flash(f'Promo code: {ad.promo_code}', 'success')
    return redirect(url_for('main.cart'))


@main_bp.route('/product-media/<int:product_id>')
def product_media(product_id):
    """Serve product image bytes stored in PostgreSQL (Render-safe)."""
    product = Product.query.get_or_404(product_id)
    if not product.image_data:
        return Response(status=404)
    mimetype = product.image_mimetype or 'image/jpeg'
    return Response(product.image_data, mimetype=mimetype)


@main_bp.route('/products')
def products():
    page = request.args.get('page', 1, type=int)
    category = (request.args.get('category', '') or '').strip()
    search = (request.args.get('search', '') or '').strip()
    sort_by = request.args.get('sort', 'newest')
    
    query = Product.query.filter_by(status='active')
    
    if category:
        matched = category_match_values(category)
        if matched:
            query = query.filter(Product.category.in_(matched))
    
    if search:
        pattern = f'%{search}%'
        query = query.filter(or_(
            Product.name.ilike(pattern),
            Product.category.ilike(pattern),
            Product.description.ilike(pattern),
        ))
    
    # Sorting
    if sort_by == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'name':
        query = query.order_by(Product.name.asc())
    else:  # newest
        query = query.order_by(Product.created_at.desc())
    
    products = query.paginate(page=page, per_page=12, error_out=False)
    
    current_category_slug = category_slug(normalize_category(category)) if category else ''
    
    return render_template('main/products.html', 
                         products=products,
                         categories=categories_for_template(),
                         current_category_slug=current_category_slug,
                         current_search=search,
                         current_sort=sort_by)

@main_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Check for active discount from session (from advertisement click)
    active_discount = session.get('active_discount', {})
    discount_info = None
    
    if active_discount and active_discount.get('ad_id'):
        ad = SellerAdvertisement.query.filter_by(
            id=active_discount['ad_id'],
            product_id=product_id,
            is_active=True,
            is_approved=True,
        ).first()

        if ad and is_advertisement_visible(ad)['visible']:
            discount_info = {
                'percentage': ad.discount_percentage,
                'discounted_price': float(ad.discounted_price),
                'expires_at': ad.expires_at,
                'ad_id': ad.id,
                'source': 'seller',
            }
        else:
            session.pop('active_discount', None)

    if not discount_info and session.get('admin_store_promo_unlocked'):
        ap = session.get('active_admin_promo') or {}
        aid = ap.get('admin_ad_id')
        if aid:
            aad = Advertisement.query.filter_by(id=aid, is_active=True).first()
            if aad and is_admin_site_advertisement_claimable(aad):
                pct = int(aad.discount_percentage)
                base = float(product.price)
                discount_info = {
                    'percentage': pct,
                    'discounted_price': round(base * (1 - pct / 100.0), 2),
                    'expires_at': aad.expires_at,
                    'ad_id': None,
                    'source': 'admin',
                }
            else:
                session.pop('active_admin_promo', None)
                session.pop('admin_store_promo_unlocked', None)

    # Get reviews for this product
    reviews = Review.query.filter_by(product_id=product_id).order_by(Review.created_at.desc()).all()
    
    # Calculate average rating
    avg_rating = db.session.query(func.avg(Review.rating)).filter_by(product_id=product_id).scalar() or 0
    
    # Get related products
    related_products = Product.query.filter(
        Product.category == product.category,
        Product.id != product_id,
        Product.status == 'active'
    ).limit(4).all()
    
    seller = User.query.get(product.seller_id) if product.seller_id else None

    return render_template('main/product_detail.html',
                         product=product,
                         seller=seller,
                         reviews=reviews,
                         avg_rating=avg_rating,
                         related_products=related_products,
                         discount_info=discount_info)

@main_bp.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Please login to add items to cart',
        }), 401

    if session.get('user_type') != 'buyer':
        return jsonify({
            'success': False,
            'message': 'Only buyer accounts can add items to the cart.',
        }), 403

    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    if not payload.get('product_id') and request.form:
        payload = {
            'product_id': request.form.get('product_id'),
            'quantity': request.form.get('quantity', 1),
        }

    product_id = payload.get('product_id')
    quantity = payload.get('quantity', 1)

    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid product.'}), 400

    # Convert quantity to integer and validate
    try:
        quantity = int(quantity)
        if quantity <= 0:
            return jsonify({'success': False, 'message': 'Quantity must be at least 1'})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid quantity value'})

    for attempt in range(5):
        try:
            # Get product (re-query each attempt so objects are bound after session.remove)
            product = Product.query.get(product_id)
            if not product:
                return jsonify({'success': False, 'message': 'Product not found'})

            if product.status != 'active':
                return jsonify({'success': False, 'message': 'Product is not available'})

            if product.stock_quantity <= 0:
                return jsonify({'success': False, 'message': 'Product is out of stock'})

            if quantity > product.stock_quantity:
                return jsonify({
                    'success': False,
                    'message': f'Only {product.stock_quantity} items available in stock',
                })

            active_discount = session.get('active_discount', {})
            discount_info = None

            if active_discount and active_discount.get('ad_id'):
                ad = SellerAdvertisement.query.filter_by(
                    id=active_discount['ad_id'],
                    product_id=product_id,
                    is_active=True,
                    is_approved=True,
                ).first()
                if ad and is_advertisement_visible(ad)['visible']:
                    discount_info = {
                        'percentage': ad.discount_percentage,
                        'discounted_price': float(ad.discounted_price),
                        'ad_id': ad.id,
                        'source': 'seller',
                    }

            if not discount_info and session.get('admin_store_promo_unlocked'):
                ap = session.get('active_admin_promo') or {}
                aid = ap.get('admin_ad_id')
                if aid:
                    aad = Advertisement.query.filter_by(id=aid, is_active=True).first()
                    if aad and is_admin_site_advertisement_claimable(aad):
                        pct = int(aad.discount_percentage)
                        base = float(product.price)
                        discount_info = {
                            'percentage': pct,
                            'discounted_price': round(base * (1 - pct / 100.0), 2),
                            'ad_id': None,
                            'source': 'admin',
                        }
                    else:
                        session.pop('active_admin_promo', None)
                        session.pop('admin_store_promo_unlocked', None)

            cart = Cart.query.filter_by(user_id=user_id).first()
            if not cart:
                cart = Cart(user_id=user_id)
                db.session.add(cart)
            db.session.flush()

            cart_item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()

            if cart_item:
                new_quantity = cart_item.quantity + quantity
                if new_quantity > product.stock_quantity:
                    return jsonify({
                        'success': False,
                        'message': f'Cannot add more. Only {product.stock_quantity} items available in stock',
                    })
                cart_item.quantity = new_quantity
                if discount_info:
                    if discount_info.get('ad_id') is not None:
                        cart_item.discount_percentage = discount_info['percentage']
                        cart_item.discounted_price = discount_info['discounted_price']
                        cart_item.advertisement_id = discount_info['ad_id']
                    elif not cart_item.advertisement_id:
                        cart_item.discount_percentage = discount_info['percentage']
                        cart_item.discounted_price = discount_info['discounted_price']
                        cart_item.advertisement_id = None
            else:
                cart_item = CartItem(
                    cart_id=cart.id,
                    product_id=product_id,
                    quantity=quantity,
                    discount_percentage=discount_info['percentage'] if discount_info else 0,
                    discounted_price=discount_info['discounted_price'] if discount_info else float(product.price),
                    advertisement_id=discount_info.get('ad_id') if discount_info else None,
                )
                db.session.add(cart_item)

            db.session.commit()
            return jsonify({'success': True, 'message': 'Item added to cart successfully'})
        except (OperationalError, DisconnectionError):
            db.session.rollback()
            db.session.remove()
            try:
                db.engine.dispose()
            except Exception:
                pass
            if attempt < 4:
                time.sleep(0.12 * (attempt + 1))

    return jsonify({
        'success': False,
        'message': 'Database temporarily unavailable. Please try again in a moment.',
    }), 503

@main_bp.route('/apply-store-promo-code', methods=['POST'])
def apply_store_promo_code():
    """Buyer enters admin store promo code at cart; unlocks session and applies % to eligible lines."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first.'}), 401
    if session.get('user_type') != 'buyer':
        return jsonify({'success': False, 'message': 'Only buyers can use store promo codes.'}), 403

    payload = request.get_json(silent=True) or {}
    code = (
        (payload.get('promo_code') or payload.get('code') or '').strip()
        or (request.form.get('promo_code') or request.form.get('code') or '').strip()
    )
    ad = find_claimable_admin_advertisement_by_promo_code(code)
    if not ad:
        return jsonify({
            'success': False,
            'message': (
                'Invalid or expired code, or that store banner has no Promo code in Admin. '
                'Set Promo code on the advertisement, then use the same code here.'
            ),
        }), 400

    session['admin_store_promo_unlocked'] = True
    session['active_admin_promo'] = {'admin_ad_id': ad.id}
    session.modified = True
    apply_admin_promo_to_buyer_cart(session['user_id'], ad)
    db.session.commit()

    label = ad.promo_code or 'STORE'
    return jsonify({
        'success': True,
        'message': f'Store promo {label} applied ({ad.discount_percentage}% off eligible cart lines).',
    })

@main_bp.route('/cart')
def cart():
    if 'user_id' not in session:
        flash('Please login to view your cart.', 'warning')
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    cart = Cart.query.filter_by(user_id=user_id).first()
    
    if not cart:
        cart_items = []
        total = 0
        total_savings = 0
    else:
        if session.get('user_type') == 'buyer':
            reconcile_buyer_cart_promos_from_session(user_id, session)
            db.session.commit()
        cart_items = CartItem.query.filter_by(cart_id=cart.id).all()
        # Calculate total using discounted prices
        total = sum((item.discounted_price or item.product.price) * item.quantity for item in cart_items)
        # Calculate total savings
        total_savings = sum((item.product.price - (item.discounted_price or item.product.price)) * item.quantity for item in cart_items)
    
    return render_template('main/cart.html', cart_items=cart_items, total=total, total_savings=total_savings)

@main_bp.route('/update-cart', methods=['POST'])
def update_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login'})
    
    cart_item_id = request.json.get('cart_item_id')
    quantity = request.json.get('quantity')
    
    # Convert quantity to integer and validate
    try:
        quantity = int(quantity)
        if quantity < 0:
            return jsonify({'success': False, 'message': 'Quantity cannot be negative'})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid quantity value'})
    
    cart_item = CartItem.query.get(cart_item_id)
    if cart_item and cart_item.cart.user_id == session['user_id']:
        if quantity <= 0:
            db.session.delete(cart_item)
        else:
            # Check if requested quantity exceeds available stock
            if quantity > cart_item.product.stock_quantity:
                return jsonify({'success': False, 'message': f'Only {cart_item.product.stock_quantity} items available in stock'})
            cart_item.quantity = quantity
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Item not found'})

@main_bp.route('/remove-from-cart', methods=['POST'])
def remove_from_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login'})
    
    cart_item_id = request.json.get('cart_item_id')
    
    cart_item = CartItem.query.get(cart_item_id)
    if cart_item and cart_item.cart.user_id == session['user_id']:
        db.session.delete(cart_item)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Item not found'})

@main_bp.route('/about')
def about():
    return render_template('main/about.html')

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        
        # Here you would typically send an email or save to database
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('main.contact'))
    
    return render_template('main/contact.html')

@main_bp.route('/privacy-policy')
def privacy_policy():
    return render_template('main/privacy_policy.html')

@main_bp.route('/terms-of-service')
def terms_of_service():
    return render_template('main/terms_of_service.html')

@main_bp.route('/api/notifications/count')
def notification_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})

    count = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
    return jsonify({'count': count})


@main_bp.route('/api/notifications/recent')
def recent_notifications():
    if 'user_id' not in session:
        return jsonify({'notifications': []})

    notifications = Notification.query.filter_by(user_id=session['user_id']).order_by(
        Notification.created_at.desc()
    ).limit(5).all()

    payload = []
    for item in notifications:
        payload.append({
            'title': item.title,
            'message': item.message,
            'notification_type': item.notification_type,
            'is_read': bool(item.is_read),
            'created_at': format_ph_datetime(item.created_at, '%b %d, %Y %I:%M %p') if item.created_at else '',
        })

    return jsonify({'notifications': payload})


@main_bp.route('/api/mobile/products')
def mobile_products():
    category = (request.args.get('category', '') or '').strip()
    search = (request.args.get('search', '') or '').strip()
    sort_by = request.args.get('sort', 'newest')

    query = Product.query.filter_by(status='active')
    if category:
        matched_categories = category_match_values(category)
        if matched_categories:
            query = query.filter(Product.category.in_(matched_categories))
    if search:
        pattern = f'%{search}%'
        query = query.filter(or_(
            Product.name.ilike(pattern),
            Product.category.ilike(pattern),
            Product.description.ilike(pattern),
        ))

    if sort_by == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'name':
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.limit(100).all()
    product_ids = [p.id for p in products]
    stats_map = {}
    if product_ids:
        rows = db.session.query(
            Review.product_id,
            func.avg(Review.rating).label('avg_r'),
            func.count(Review.id).label('review_ct'),
        ).filter(Review.product_id.in_(product_ids)).group_by(Review.product_id).all()
        for row in rows:
            stats_map[row.product_id] = (
                float(row.avg_r or 0),
                int(row.review_ct or 0),
            )
    payload = [
        _product_to_dict_for_mobile(p, *stats_map.get(p.id, (0.0, 0)))
        for p in products
    ]
    return jsonify({'products': payload})


@main_bp.route('/api/mobile/products/<int:product_id>')
def mobile_product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    avg_rating = db.session.query(func.avg(Review.rating)).filter_by(product_id=product_id).scalar() or 0
    review_count = Review.query.filter_by(product_id=product_id).count()
    seller = User.query.get(product.seller_id)
    seller_name = 'Seller'
    if seller:
        seller_name = (f'{seller.first_name or ""} {seller.last_name or ""}'.strip()
                       or seller.email or 'Seller')

    review_rows = (
        Review.query.filter_by(product_id=product_id)
        .order_by(Review.created_at.desc())
        .limit(50)
        .all()
    )
    reviews_out = []
    for r in review_rows:
        bu = User.query.get(r.user_id)
        rname = 'Buyer'
        if bu:
            rname = (
                f'{bu.first_name or ""} {bu.last_name or ""}'.strip()
                or bu.email
                or 'Buyer'
            )
        reviews_out.append({
            'rating': r.rating,
            'comment': r.comment or '',
            'reviewer_name': rname,
            'created_at': isoformat_utc_z(r.created_at) if r.created_at else None,
        })

    return jsonify({
        'product': _product_to_dict_for_mobile(product, float(avg_rating or 0), review_count),
        'avg_rating': float(avg_rating or 0),
        'review_count': review_count,
        'seller': {
            'id': seller.id if seller else 0,
            'display_name': seller_name,
        },
        'reviews': reviews_out,
    })


@main_bp.route('/api/mobile/cart')
def mobile_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login'}), 401

    user_id = session['user_id']
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        return jsonify({'items': [], 'total': 0.0, 'total_savings': 0.0})

    # Same as web `/cart`: seller session promo + admin only after promo code at cart.
    if session.get('user_type') == 'buyer':
        reconcile_buyer_cart_promos_from_session(user_id, session)
        db.session.commit()

    return jsonify(mobile_cart_snapshot_json(user_id))


@main_bp.route('/api/mobile/cart/add', methods=['POST'])
def mobile_add_to_cart():
    return add_to_cart()


@main_bp.route('/api/mobile/cart/update', methods=['POST'])
def mobile_update_cart():
    return update_cart()


@main_bp.route('/api/mobile/cart/remove', methods=['POST'])
def mobile_remove_from_cart():
    return remove_from_cart()

@main_bp.route('/chat-support')
def user_chat_support():
    if 'user_id' not in session:
        flash('Please login to access chat support.', 'warning')
        return redirect(url_for('auth.login'))
    
    update_user_activity()  # Update user activity when accessing chat support
    
    user_id = session['user_id']
    
    # Get user's chat rooms with admin
    chat_rooms = ChatRoom.query.filter(
        (ChatRoom.buyer_id == user_id) |
        (ChatRoom.seller_id == user_id) |
        (ChatRoom.rider_id == user_id)
    ).filter(ChatRoom.room_type == 'admin_support').order_by(ChatRoom.created_at.desc()).all()
    
    # Get current chat room if specified
    current_room_id = request.args.get('room_id')
    current_room = None
    messages = []
    
    if current_room_id:
        current_room = ChatRoom.query.get(current_room_id)
        if current_room and (current_room.buyer_id == user_id or current_room.seller_id == user_id or current_room.rider_id == user_id):
            messages = ChatMessage.query.filter_by(chat_room_id=current_room_id).order_by(ChatMessage.created_at.asc()).all()
    
    return render_template('main/chat_support.html', 
                         chat_rooms=chat_rooms,
                         current_room=current_room,
                         messages=messages)

@main_bp.route('/chat-support/start-chat', methods=['POST'])
def user_start_chat():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    user_id = session['user_id']
    
    # Get admin user
    admin = User.query.filter_by(user_type='admin').first()
    if not admin:
        return jsonify({'success': False, 'message': 'No admin available'})
    
    # Check if chat room already exists (check all possible combinations)
    existing_room = ChatRoom.query.filter(
        (ChatRoom.room_type == 'admin_support') &
        (
            # Admin as seller, user as buyer
            ((ChatRoom.seller_id == admin.id) & (ChatRoom.buyer_id == user_id)) |
            # Admin as buyer, user as seller  
            ((ChatRoom.seller_id == user_id) & (ChatRoom.buyer_id == admin.id)) |
            # Admin as rider, user as buyer
            ((ChatRoom.rider_id == admin.id) & (ChatRoom.buyer_id == user_id)) |
            # Admin as buyer, user as rider
            ((ChatRoom.rider_id == user_id) & (ChatRoom.buyer_id == admin.id)) |
            # Admin as seller, user as rider
            ((ChatRoom.seller_id == admin.id) & (ChatRoom.rider_id == user_id)) |
            # Admin as rider, user as seller
            ((ChatRoom.seller_id == user_id) & (ChatRoom.rider_id == admin.id))
        )
    ).first()
    
    if existing_room:
        return jsonify({'success': True, 'room_id': existing_room.id})
    
    # Create new chat room based on user type
    user = User.query.get(user_id)
    room_name = f"Support Chat - {user.first_name} {user.last_name}"
    
    # Create room based on user type
    if user.user_type == 'buyer':
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            buyer_id=user_id,
            seller_id=admin.id
        )
    elif user.user_type == 'seller':
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            seller_id=user_id,
            buyer_id=admin.id
        )
    elif user.user_type == 'rider':
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            rider_id=user_id,
            buyer_id=admin.id
        )
    else:
        # Default to buyer for unknown types
        new_room = ChatRoom(
            room_name=room_name,
            room_type='admin_support',
            buyer_id=user_id,
            seller_id=admin.id
        )
    
    db.session.add(new_room)
    db.session.commit()
    
    return jsonify({'success': True, 'room_id': new_room.id})

@main_bp.route('/chat-support/send-message', methods=['POST'])
def user_send_message():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    room_id = request.json.get('room_id')
    message_text = request.json.get('message')
    sender_id = session.get('user_id')
    
    if not room_id or not message_text:
        return jsonify({'success': False, 'message': 'Room ID and message are required'})
    
    # Verify the user is part of this chat room
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

@main_bp.route('/chat-support/get-messages/<int:room_id>')
def user_get_messages(room_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    # Verify the user is part of this chat room
    room = ChatRoom.query.get(room_id)
    user_id = session.get('user_id')
    
    if not room or (room.seller_id != user_id and room.buyer_id != user_id and room.rider_id != user_id):
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