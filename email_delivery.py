"""
OTP / transactional email delivery.

Priority:
1. Resend HTTP API (works on Render; set RESEND_API_KEY)
2. Flask-Mail SMTP (local dev)
3. Inline OTP on screen (MAIL_FAIL_OPEN / Render fallback)
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def resend_configured(app) -> bool:
    return bool((app.config.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY", "")).strip())


def smtp_configured(app) -> bool:
    user = app.config.get("MAIL_USERNAME") or ""
    pwd = app.config.get("MAIL_PASSWORD") or ""
    return user not in ("", "your-email@gmail.com") and pwd not in ("", "your-app-password")


def should_skip_smtp(app) -> bool:
    if resend_configured(app):
        return False
    if os.environ.get("RENDER", "").strip():
        return True
    if os.environ.get("MAIL_SUPPRESS_SEND", "").lower() in ("1", "true", "yes"):
        return True
    if app.config.get("MAIL_FAIL_OPEN") and os.environ.get("FLASK_ENV") == "production":
        return True
    return False


def send_html_email(app, *, to_email: str, subject: str, html: str) -> bool:
    if resend_configured(app):
        return _send_via_resend(app, to_email=to_email, subject=subject, html=html)
    if not smtp_configured(app):
        logger.warning("Email not configured (no Resend key, no SMTP credentials).")
        return False
    if should_skip_smtp(app):
        logger.info("SMTP skipped for %s (set RESEND_API_KEY on cloud hosts).", to_email)
        return False
    return _send_via_smtp(app, to_email=to_email, subject=subject, html=html)


def _send_via_resend(app, *, to_email: str, subject: str, html: str) -> bool:
    api_key = (app.config.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY", "")).strip()
    from_addr = (
        app.config.get("RESEND_FROM")
        or os.environ.get("RESEND_FROM")
        or "Sports & Outdoors <onboarding@resend.dev>"
    ).strip()
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"from": from_addr, "to": [to_email], "subject": subject, "html": html},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            logger.info("Resend email sent to %s", to_email)
            return True
        logger.error("Resend failed (%s): %s", resp.status_code, resp.text[:500])
        return False
    except requests.RequestException as exc:
        logger.exception("Resend request error: %s", exc)
        return False


def _send_via_smtp(app, *, to_email: str, subject: str, html: str) -> bool:
    from flask_mail import Message

    from app import mail

    try:
        msg = Message(subject, sender=app.config["MAIL_USERNAME"], recipients=[to_email])
        msg.html = html
        mail.send(msg)
        logger.info("SMTP email sent to %s", to_email)
        return True
    except Exception as exc:
        logger.exception("SMTP send failed for %s: %s", to_email, exc)
        return False


def otp_email_html(
    *,
    title: str,
    heading: str,
    body: str,
    otp_code: str,
    action_link: str,
    accent: str = "#28a745",
) -> str:
    parts = [
        "<!DOCTYPE html><html><body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;'>",
        f"<div style='background:{accent};color:#fff;padding:20px;text-align:center;border-radius:10px 10px 0 0;'>",
        f"<h1 style='margin:0;font-size:22px;'>{title}</h1></div>",
        "<div style='background:#f8f9fa;padding:30px;border-radius:0 0 10px 10px;'>",
        f"<h2 style='color:#333;'>{heading}</h2><p>{body}</p>",
        "<div style='text-align:center;margin:24px 0;background:#fff;border:1px solid #ddd;border-radius:8px;padding:20px;'>",
        f"<div style='font-size:32px;letter-spacing:8px;font-weight:bold;color:{accent};'>{otp_code}</div>",
        "</div>",
        f"<p style='color:#666;font-size:14px;'><a href='{action_link}'>{action_link}</a></p>",
        "<p style='color:#666;font-size:14px;'><strong>Expires in 10 minutes.</strong></p>",
        "</div></body></html>",
    ]
    return "".join(parts)
