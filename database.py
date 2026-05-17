import os

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import DECIMAL, or_

# Initialize SQLAlchemy
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    address_region = db.Column(db.String(100), nullable=False)
    address_province = db.Column(db.String(100), nullable=False)
    address_city = db.Column(db.String(100), nullable=False)
    address_barangay = db.Column(db.String(100), nullable=False)
    address_street = db.Column(db.String(255), default='')
    user_type = db.Column(
        db.Enum('buyer', 'seller', 'admin', 'rider', name='user_type_enum'),
        nullable=False
    )
    is_verified = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    profile_picture = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Seller specific fields
    business_permit = db.Column(db.String(255))
    product_categories = db.Column(db.Text)  # JSON string of categories
    
    # Rider specific fields
    drivers_license = db.Column(db.String(255))
    vehicle_type = db.Column(db.String(50))
    vehicle_plate = db.Column(db.String(20))
    
    # Relationships
    products = db.relationship('Product', backref='seller', lazy=True)
    orders = db.relationship('Order', backref='buyer', lazy=True)
    deliveries = db.relationship('Delivery', backref='rider', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(DECIMAL(10, 2), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(255))
    status = db.Column(
        db.Enum('active', 'inactive', 'archived', name='product_status_enum'),
        default='active'
    )
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    reviews = db.relationship('Review', backref='product', lazy=True)
    cart_items = db.relationship('CartItem', backref='product', lazy=True)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    # Discount information
    discount_percentage = db.Column(db.Integer, default=0)  # 0-100
    discounted_price = db.Column(DECIMAL(10, 2), nullable=True)  # NULL means no discount
    advertisement_id = db.Column(db.Integer, db.ForeignKey('seller_advertisement.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def apply_seller_ad_to_buyer_cart_items(user_id, advertisement):
    """
    Apply a seller advertisement's fixed sale price to every cart line for that product.
    Caller commits.
    """
    if not user_id or not advertisement:
        return
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        return
    for item in CartItem.query.filter_by(cart_id=cart.id, product_id=advertisement.product_id).all():
        item.discount_percentage = advertisement.discount_percentage
        item.discounted_price = float(advertisement.discounted_price)
        item.advertisement_id = advertisement.id


def apply_admin_promo_to_buyer_cart(user_id, advertisement):
    """
    Apply admin site-wide discount % to cart lines that are not tied to a seller ad.
    Caller commits.
    """
    if not user_id or not advertisement:
        return
    pct = int(advertisement.discount_percentage or 0)
    if pct <= 0:
        return
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        return
    factor = 1.0 - (pct / 100.0)
    for item in CartItem.query.filter_by(cart_id=cart.id).all():
        if item.advertisement_id is not None:
            continue
        base = float(item.product.price)
        item.discount_percentage = pct
        item.discounted_price = round(base * factor, 2)


def reset_cart_lines_admin_store_discount_only(user_id):
    """
    Remove admin site-wide pricing from cart lines (any line not tied to a seller ad).
    Seller-ad lines are unchanged. Caller commits.
    """
    if not user_id:
        return
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        return
    for item in CartItem.query.filter_by(cart_id=cart.id).all():
        if item.advertisement_id is not None:
            continue
        item.discount_percentage = 0
        item.discounted_price = float(item.product.price)


def reconcile_buyer_cart_promos_from_session(user_id, session):
    """
    Buyer cart: clear admin store pricing unless ``admin_store_promo_unlocked`` (promo code path);
    re-apply seller session deal; re-apply admin if unlocked. May pop stale session keys.
    Caller commits.
    """
    from timezone_utils import is_advertisement_visible, is_admin_site_advertisement_claimable

    if not user_id or session.get('user_type') != 'buyer':
        return
    if not session.get('admin_store_promo_unlocked'):
        reset_cart_lines_admin_store_discount_only(user_id)
        session.pop('active_admin_promo', None)
    sid = (session.get('active_discount') or {}).get('ad_id')
    if sid:
        sad = SellerAdvertisement.query.filter_by(
            id=sid, is_active=True, is_approved=True
        ).first()
        if sad and is_advertisement_visible(sad)['visible']:
            apply_seller_ad_to_buyer_cart_items(user_id, sad)
    if session.get('admin_store_promo_unlocked'):
        aid = (session.get('active_admin_promo') or {}).get('admin_ad_id')
        if aid:
            aad = Advertisement.query.filter_by(id=aid, is_active=True).first()
            if aad and is_admin_site_advertisement_claimable(aad):
                apply_admin_promo_to_buyer_cart(user_id, aad)
            else:
                session.pop('active_admin_promo', None)
                session.pop('admin_store_promo_unlocked', None)


def seller_display_name(user):
    """Same label as GET /api/mobile/products/<id> `seller.display_name`."""
    if not user:
        return 'Seller'
    named = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    return named or (user.email or '').strip() or 'Seller'


def order_pickup_shop_labels(order):
    """Unique seller shop names for an order's line items (joined with ·)."""
    if not order:
        return ''
    labels = []
    seen = set()
    for oi in order.items or []:
        prod = getattr(oi, 'product', None)
        if not prod:
            continue
        sid = prod.seller_id
        if sid is None or sid in seen:
            continue
        seen.add(sid)
        seller = getattr(prod, 'seller', None)
        labels.append(seller_display_name(seller))
    return ' · '.join(labels) if labels else ''


def _delivered_order_ids_subquery():
    """Order IDs whose delivery row is completed (even if order.status lags)."""
    return db.session.query(Delivery.order_id).filter(Delivery.status == 'delivered')


def effective_order_status(order):
    """
    Status shown in lists/tabs. Delivery completed ⇒ treat as delivered unless
    order was cancelled/refunded.
    """
    if not order:
        return ''
    raw = (getattr(order, 'status', None) or '').strip().lower()
    if raw in ('cancelled', 'refunded'):
        return raw
    delivery = getattr(order, 'delivery', None)
    if delivery and (delivery.status or '').strip().lower() == 'delivered':
        return 'delivered'
    return getattr(order, 'status', None) or ''


def sync_order_status_with_delivery(order):
    """Persist order.status=delivered when delivery is already completed."""
    if not order:
        return False
    raw = (order.status or '').strip().lower()
    if raw in ('cancelled', 'refunded', 'delivered'):
        return False
    delivery = getattr(order, 'delivery', None)
    if delivery and (delivery.status or '').strip().lower() == 'delivered':
        order.status = 'delivered'
        return True
    return False


def repair_delivered_order_status_mismatches():
    """
    Fix legacy rows: delivery.status=delivered but order.status still shipped/etc.
    Returns number of orders repaired.
    """
    delivered_ids = _delivered_order_ids_subquery()
    rows = Order.query.filter(
        Order.id.in_(delivered_ids),
        ~Order.status.in_(('delivered', 'cancelled', 'refunded')),
    ).all()
    for order in rows:
        order.status = 'delivered'
    if rows:
        db.session.commit()
    return len(rows)


def filter_orders_by_tab(query, status_filter):
    """
    Apply My Orders / admin tab filters using order.status + delivery.status so
    completed deliveries always appear under Delivered.
    """
    sf = (status_filter or 'all').strip().lower()
    if sf == 'all':
        return query
    delivered_sq = _delivered_order_ids_subquery()
    if sf == 'preparing':
        return query.filter(
            Order.status.in_(('confirmed', 'preparing')),
            ~Order.id.in_(delivered_sq),
        )
    if sf == 'shipped':
        return query.filter(
            Order.status == 'shipped',
            ~Order.id.in_(delivered_sq),
        )
    if sf == 'delivered':
        return query.filter(
            or_(
                Order.status == 'delivered',
                Order.id.in_(delivered_sq),
            )
        )
    return query.filter(Order.status == sf)


def mobile_cart_snapshot_json(user_id):
    """
    Current cart as the same JSON shape as GET /api/mobile/cart (items, total, total_savings).
    Does not run session reconcile — use right after mutating cart lines so mobile clients
    can refresh prices without relying on Set-Cookie round-trips.
    """
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        return {'items': [], 'total': 0.0, 'total_savings': 0.0}
    items = []
    total = 0.0
    total_savings = 0.0
    for item in CartItem.query.filter_by(cart_id=cart.id).all():
        p = item.product
        unit_price = float(item.discounted_price or p.price)
        original_price = float(p.price)
        line_total = unit_price * item.quantity
        total += line_total
        total_savings += (original_price - unit_price) * item.quantity
        shop_name = seller_display_name(getattr(p, 'seller', None))
        items.append({
            'id': item.id,
            'product_id': item.product_id,
            'product_name': p.name,
            'category': p.category,
            'image_url': p.image_url,
            'seller_id': p.seller_id,
            'shop_name': shop_name,
            'quantity': item.quantity,
            'stock_quantity': p.stock_quantity,
            'unit_price': unit_price,
            'original_price': original_price,
            'discount_percentage': item.discount_percentage,
            'line_total': line_total,
        })
    return {'items': items, 'total': total, 'total_savings': total_savings}


def normalize_admin_promo_code(raw):
    if raw is None:
        return None
    s = str(raw).strip().upper()
    return s or None


def find_claimable_admin_advertisement_by_promo_code(raw_code):
    """
    Match an active admin Advertisement by its promo_code (case-insensitive, trimmed).
    Uses same validity window as home banners (is_admin_site_advertisement_claimable).
    """
    from sqlalchemy import and_, func

    from timezone_utils import is_admin_site_advertisement_claimable

    norm = normalize_admin_promo_code(raw_code)
    if not norm:
        return None
    # DB may store mixed case or stray spaces from older imports — normalize in SQL.
    candidates = (
        Advertisement.query.filter(
            and_(
                Advertisement.is_active == True,  # noqa: E712
                Advertisement.promo_code.isnot(None),
                func.upper(func.trim(Advertisement.promo_code)) == norm,
            )
        )
        .order_by(Advertisement.id.desc())
        .all()
    )
    for ad in candidates:
        if is_admin_site_advertisement_claimable(ad):
            return ad
    return None


def seller_advertisement_image_abs_path(image_url):
    """
    Map SellerAdvertisement.image_url to a path under static/.
    Supports `uploads/advertisements/...` (canonical) and legacy `advertisements/...`.
    """
    if not image_url:
        return None
    url = str(image_url).replace("\\", "/").strip().lstrip("/")
    if url.startswith("uploads/"):
        return os.path.join("static", url)
    return os.path.join("static", "uploads", url)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(DECIMAL(10, 2), nullable=False)
    status = db.Column(
        db.Enum(
            'pending',
            'confirmed',
            'preparing',
            'shipped',
            'delivered',
            'cancelled',
            'refunded',
            name='order_status_enum'
        ),
        default='pending'
    )
    payment_method = db.Column(db.String(50), default='cash_on_delivery')
    shipping_address = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    delivery = db.relationship('Delivery', backref='order', lazy=True, uselist=False)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(DECIMAL(10, 2), nullable=False)  # Final price paid (discounted if applicable)
    # Discount information
    original_price = db.Column(DECIMAL(10, 2), nullable=True)  # Original product price
    discount_percentage = db.Column(db.Integer, default=0)  # 0-100
    advertisement_id = db.Column(db.Integer, db.ForeignKey('seller_advertisement.id'), nullable=True)

def clear_seller_advertisement_fk_before_delete(advertisement_id):
    """
    Remove FK references so a SellerAdvertisement row can be deleted.
    Cart lines revert to the product's current list price; order history keeps amounts, drops FK only.
    """
    if not advertisement_id:
        return
    for item in CartItem.query.filter_by(advertisement_id=advertisement_id).all():
        item.advertisement_id = None
        item.discount_percentage = 0
        item.discounted_price = float(item.product.price)
    for oi in OrderItem.query.filter_by(advertisement_id=advertisement_id).all():
        oi.advertisement_id = None


class Delivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(
        db.Enum(
            'pending',
            'assigned',
            'picked_up',
            'in_transit',
            'delivered',
            name='delivery_status_enum'
        ),
        default='pending'
    )
    pickup_address = db.Column(db.Text, nullable=False)
    delivery_address = db.Column(db.Text, nullable=False)
    commission_amount = db.Column(DECIMAL(10, 2), default=0.00)
    # Proof of delivery (relative to Flask static/, e.g. uploads/pod/<file>.jpg)
    pod_image_url = db.Column(db.String(500), nullable=True)
    pod_remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    # order relationship is defined in Order model

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    notification_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Advertisement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    discount_percentage = db.Column(db.Integer, default=0)
    # Buyer enters this at cart checkout (same discount rules as store-wide admin offer).
    promo_code = db.Column(db.String(64), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class Commission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    platform_commission = db.Column(DECIMAL(10, 2), nullable=False)
    rider_commission = db.Column(DECIMAL(10, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref='commission')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='seller_commissions')
    rider = db.relationship('User', foreign_keys=[rider_id], backref='rider_commissions')

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='wishlist_items')
    product = db.relationship('Product', backref='wishlist_items')
    
    # Ensure unique user-product combination
    __table_args__ = (db.UniqueConstraint('user_id', 'product_id', name='unique_user_product_wishlist'),)

class EmailVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref='email_verifications')

class ChatRoom(db.Model):
    """Chat room between users"""
    __tablename__ = 'chat_room'
    
    id = db.Column(db.Integer, primary_key=True)
    room_name = db.Column(db.String(100), nullable=False)
    room_type = db.Column(db.String(20), nullable=False)  # 'seller_rider', 'rider_buyer', 'buyer_seller'
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    seller = db.relationship('User', foreign_keys=[seller_id], backref='seller_chat_rooms')
    rider = db.relationship('User', foreign_keys=[rider_id], backref='rider_chat_rooms')
    buyer = db.relationship('User', foreign_keys=[buyer_id], backref='buyer_chat_rooms')
    order = db.relationship('Order', backref='chat_rooms')
    messages = db.relationship('ChatMessage', backref='chat_room', cascade='all, delete-orphan')

class ChatMessage(db.Model):
    """Individual chat messages"""
    __tablename__ = 'chat_message'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # 'text', 'image', 'file'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    sender = db.relationship('User', backref='sent_messages')

class SellerAdvertisement(db.Model):
    """Seller-created advertisements with discounts"""
    __tablename__ = 'seller_advertisement'
    
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    discount_percentage = db.Column(db.Integer, nullable=False)  # 1-100
    original_price = db.Column(DECIMAL(10, 2), nullable=False)
    discounted_price = db.Column(DECIMAL(10, 2), nullable=False)
    image_url = db.Column(db.String(255))
    promo_message = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=False)  # Admin approval
    starts_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    seller = db.relationship('User', backref='seller_advertisements')
    product = db.relationship('Product', backref='advertisements')