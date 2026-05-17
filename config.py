"""
Configuration file for Sports and Outdoors Ecommerce System
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _apply_render_email_fallback():
    """Inject email keys on Render when dashboard env vars are missing."""
    if not os.environ.get("RENDER", "").strip():
        return
    try:
        import render_email_defaults as _email_defaults
    except ImportError:
        return

    brevo_api = getattr(_email_defaults, "BREVO_API_KEY", "") or ""
    brevo_smtp = getattr(_email_defaults, "BREVO_SMTP_KEY", "") or ""
    resend_key = getattr(_email_defaults, "RESEND_API_KEY", "") or ""
    resend_from = getattr(_email_defaults, "RESEND_FROM", "") or ""

    if brevo_api and not os.environ.get("BREVO_API_KEY", "").strip():
        os.environ["BREVO_API_KEY"] = brevo_api
    if brevo_smtp and not os.environ.get("BREVO_SMTP_KEY", "").strip():
        os.environ["BREVO_SMTP_KEY"] = brevo_smtp
    if resend_key and not os.environ.get("RESEND_API_KEY", "").strip():
        os.environ["RESEND_API_KEY"] = resend_key
    if resend_from and not os.environ.get("RESEND_FROM"):
        os.environ["RESEND_FROM"] = resend_from


_apply_render_email_fallback()


def _build_database_url(default_url):
    """
    Build a SQLAlchemy database URL with Supabase/Postgres compatibility.
    """
    database_url = os.environ.get('DATABASE_URL') or default_url

    # Supabase can provide postgres:// URLs; SQLAlchemy expects postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    # Ensure SSL is enabled for Supabase connections.
    if 'supabase.co' in database_url and 'sslmode=' not in database_url:
        separator = '&' if '?' in database_url else '?'
        database_url = f"{database_url}{separator}sslmode=require"

    # Supavisor: 5432 is often transaction-pooling (fragile with SQLAlchemy). 6543 is session mode.
    if (
        'pooler.supabase.com' in database_url
        and ':5432' in database_url
        and os.environ.get('SUPABASE_USE_TRANSACTION_POOLER', '').lower() not in ('1', 'true', 'yes')
    ):
        database_url = database_url.replace(':5432', ':6543', 1)

    return database_url


def _engine_options_for(database_url):
    """Pool + driver options; Postgres/Supabase get shorter recycle and TCP keepalives."""
    opts = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }
    if not database_url:
        return opts
    u = database_url.lower()
    if 'sqlite' in u:
        return {'pool_pre_ping': True}
    if 'postgresql' in u or '+psycopg' in u or u.startswith('postgres:'):
        opts['pool_recycle'] = 55
        opts['connect_args'] = {
            'keepalives': 1,
            'keepalives_idle': 25,
            'keepalives_interval': 10,
            'keepalives_count': 5,
            'connect_timeout': 15,
        }
    return opts


class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this-in-production'
    SQLALCHEMY_DATABASE_URI = _build_database_url('mysql+pymysql://root:@localhost/ecommerce_system')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for(SQLALCHEMY_DATABASE_URI)
    
    # Email configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'your-email@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'your-app-password'
    MAIL_TIMEOUT = int(os.environ.get('MAIL_TIMEOUT', '8'))
    # When True, registration still works if SMTP fails (OTP shown on screen).
    MAIL_FAIL_OPEN = os.environ.get('MAIL_FAIL_OPEN', '').lower() in ('1', 'true', 'yes')
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '').strip()
    BREVO_SMTP_KEY = os.environ.get('BREVO_SMTP_KEY', '').strip()
    BREVO_SMTP_LOGIN = os.environ.get('BREVO_SMTP_LOGIN', '').strip()
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
    RESEND_FROM = os.environ.get(
        'RESEND_FROM',
        'Sports & Outdoors <onboarding@resend.dev>',
    ).strip()
    # Render sets RENDER_EXTERNAL_URL automatically (e.g. https://sports-outdoors.onrender.com).
    APP_BASE_URL = (
        os.environ.get('APP_BASE_URL')
        or os.environ.get('RENDER_EXTERNAL_URL')
        or 'http://localhost:5000'
    )
    
    # File upload configuration
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}
    
    # Pagination
    POSTS_PER_PAGE = 12
    ORDERS_PER_PAGE = 10
    
    # Commission rates
    PLATFORM_COMMISSION_RATE = 0.05  # 5%
    RIDER_COMMISSION_RATE = 0.02     # 2%

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _build_database_url('mysql+pymysql://root:@localhost/ecommerce_system')
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for(SQLALCHEMY_DATABASE_URI)

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _build_database_url('mysql+pymysql://root:@localhost/ecommerce_system')
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for(SQLALCHEMY_DATABASE_URI)
    # OTP is sent by email only unless MAIL_FAIL_OPEN=true (dev fallback).
    MAIL_FAIL_OPEN = os.environ.get('MAIL_FAIL_OPEN', 'false').lower() in ('1', 'true', 'yes')

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options_for('sqlite:///:memory:')
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
