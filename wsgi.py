"""WSGI entry point for Gunicorn on Render."""
import os

from dotenv import load_dotenv

load_dotenv()


def _apply_render_resend_fallback():
    """Use Resend on Render when dashboard env is missing (SMTP is blocked)."""
    if not os.environ.get("RENDER", "").strip():
        return
    if os.environ.get("RESEND_API_KEY", "").strip():
        return
    try:
        from render_email_defaults import RESEND_API_KEY, RESEND_FROM
    except ImportError:
        return
    if RESEND_API_KEY:
        os.environ["RESEND_API_KEY"] = RESEND_API_KEY
    if RESEND_FROM and not os.environ.get("RESEND_FROM"):
        os.environ["RESEND_FROM"] = RESEND_FROM


_apply_render_resend_fallback()

from app import app as application  # noqa: E402
