from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import secrets
from datetime import datetime, timedelta, timezone
import json
from config import config

app = Flask(__name__)

# Load configuration
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[config_name])

if config_name == 'production':
    # Render terminates TLS at the edge; trust X-Forwarded-* for HTTPS URLs and cookies.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config['SESSION_COOKIE_SECURE'] = True

# Import database and models
from database import db, User, Product, Cart, CartItem, Order, OrderItem, Delivery, Review, Notification, Advertisement, Commission, EmailVerification, ChatRoom, ChatMessage, Wishlist, SellerAdvertisement

# Initialize extensions
migrate = Migrate(app, db)
mail = Mail(app)
# Flutter web dev servers (any port) + LAN + Render HTTPS for production.
_cors_origins = [
    r"http://localhost:\d+",
    r"http://127\.0\.0\.1:\d+",
    r"http://192\.168\.\d+\.\d+:\d+",
    r"http://10\.\d+\.\d+\.\d+:\d+",
    r"http://172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+:\d+",
]
if config_name == 'production':
    _cors_origins.append(r"https://.*\.onrender\.com")
CORS(
    app,
    resources={
        r"/*": {
            "origins": _cors_origins,
        }
    },
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    expose_headers=["Set-Cookie"],
)

# Flutter web (different port) and mobile API clients need the session cookie on localhost.
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)

# Initialize database with app
db.init_app(app)

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'pod'), exist_ok=True)

# Import routes
from routes.auth import auth_bp
from routes.buyer import buyer_bp
from routes.seller import seller_bp
from routes.admin import admin_bp
from routes.rider import rider_bp
from routes.main import main_bp
from routes.seller_advertisements import seller_ad_bp
from routes.admin_advertisements import admin_ad_bp

# Register blueprints with URL prefixes
app.register_blueprint(auth_bp)
app.register_blueprint(buyer_bp, url_prefix='/buyer')
app.register_blueprint(seller_bp, url_prefix='/seller')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(rider_bp, url_prefix='/rider')
app.register_blueprint(main_bp)
app.register_blueprint(seller_ad_bp)
app.register_blueprint(admin_ad_bp)


@app.route('/health')
def health_check():
    from email_delivery import brevo_configured, email_ready, resend_configured, smtp_configured

    on_render = bool(os.environ.get('RENDER', '').strip())
    return jsonify({
        'status': 'ok',
        'on_render': on_render,
        'brevo_configured': brevo_configured(app),
        'resend_configured': resend_configured(app),
        'smtp_configured': smtp_configured(app),
        'email_ready': email_ready(app),
    }), 200


@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='images/fitness-hero.jpg'))


def ensure_advertisement_promo_code_column():
    """Add promo_code to advertisement for existing MySQL/SQLite DBs (no Alembic in repo)."""
    from sqlalchemy import inspect, text

    with app.app_context():
        try:
            insp = inspect(db.engine)
            cols = {c['name'] for c in insp.get_columns('advertisement')}
        except Exception:
            return
        if 'promo_code' in cols:
            return
        dialect = db.engine.dialect.name
        try:
            with db.engine.begin() as conn:
                if dialect == 'sqlite':
                    conn.execute(text('ALTER TABLE advertisement ADD COLUMN promo_code VARCHAR(64)'))
                else:
                    conn.execute(text('ALTER TABLE advertisement ADD COLUMN promo_code VARCHAR(64) NULL'))
        except Exception as e:
            app.logger.warning('Could not add advertisement.promo_code: %s', e)


def ensure_delivery_pod_columns():
    """Add proof-of-delivery columns to delivery for existing DBs."""
    from sqlalchemy import inspect, text

    with app.app_context():
        try:
            insp = inspect(db.engine)
            cols = {c['name'] for c in insp.get_columns('delivery')}
        except Exception:
            return
        dialect = db.engine.dialect.name
        try:
            with db.engine.begin() as conn:
                if 'pod_image_url' not in cols:
                    if dialect == 'sqlite':
                        conn.execute(text('ALTER TABLE delivery ADD COLUMN pod_image_url VARCHAR(500)'))
                    else:
                        conn.execute(text('ALTER TABLE delivery ADD COLUMN pod_image_url VARCHAR(500) NULL'))
                if 'pod_remarks' not in cols:
                    if dialect == 'sqlite':
                        conn.execute(text('ALTER TABLE delivery ADD COLUMN pod_remarks TEXT'))
                    else:
                        conn.execute(text('ALTER TABLE delivery ADD COLUMN pod_remarks TEXT NULL'))
        except Exception as e:
            app.logger.warning('Could not add delivery POD columns: %s', e)


def ensure_delivered_order_status_synced():
    """Align order.status with completed deliveries (legacy rows + on startup)."""
    from database import repair_delivered_order_status_mismatches

    with app.app_context():
        try:
            n = repair_delivered_order_status_mismatches()
            if n:
                app.logger.info('Repaired %s order(s) marked delivered from delivery status.', n)
        except Exception as e:
            app.logger.warning('Could not repair delivered order statuses: %s', e)


def run_startup_db_tasks():
    """Schema repair / sync — skip on Gunicorn production boot (Supabase already migrated)."""
    ensure_advertisement_promo_code_column()
    ensure_delivery_pod_columns()
    ensure_delivered_order_status_synced()


def _should_run_startup_db_tasks():
    if config_name != 'production':
        return True
    return os.environ.get('RUN_STARTUP_DB', '').lower() in ('1', 'true', 'yes')


if _should_run_startup_db_tasks():
    try:
        run_startup_db_tasks()
    except Exception:
        pass

PH_TZ = timezone(timedelta(hours=8))


def _as_ph_time(value):
    if value is None:
        return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        # DB values are stored as naive UTC datetimes in this project.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(PH_TZ)


@app.template_filter('datetime')
def datetime_filter(value, fmt='%B %d, %Y %I:%M %p'):
    dt = _as_ph_time(value)
    if dt is None:
        return ""
    return dt.strftime(fmt)


@app.template_filter('ph_date')
def ph_date_filter(value, fmt='%B %d, %Y'):
    dt = _as_ph_time(value)
    if dt is None:
        return ""
    return dt.strftime(fmt)


@app.template_filter('ph_time')
def ph_time_filter(value, fmt='%I:%M %p'):
    dt = _as_ph_time(value)
    if dt is None:
        return ""
    return dt.strftime(fmt)


@app.template_filter('ph_datetime_local')
def ph_datetime_local_filter(value):
    """Value for HTML datetime-local (Philippine wall clock)."""
    dt = _as_ph_time(value)
    if dt is None:
        return ""
    return dt.strftime('%Y-%m-%dT%H:%M')


@app.template_filter('order_status')
def order_status_filter(order):
    """Display status (order + delivery); use in templates instead of raw order.status."""
    from database import effective_order_status
    return effective_order_status(order)


@app.template_filter('order_status_label')
def order_status_label_filter(order):
    s = order_status_filter(order)
    return (s or '').replace('_', ' ').title()


@app.template_filter('iso_utc')
def iso_utc_filter(value):
    """ISO 8601 with Z for <script> / JS (naive DB datetimes = UTC)."""
    from timezone_utils import isoformat_utc_z
    return isoformat_utc_z(value) or ''


@app.template_filter('currency')
def currency_filter(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = 0.0
    return f"₱{n:,.2f}"

if __name__ == '__main__':
    with app.app_context():
        run_startup_db_tasks()
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
