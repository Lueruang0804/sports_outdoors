"""
Send OTP / transactional email.

Order:
1. Gmail SMTP from MAIL_* in .env (works on local PC)
2. Resend HTTP API if RESEND_API_KEY is set (works on Render — SMTP is blocked there)
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)

# Set when Resend returns an API error (for user-facing messages).
last_send_error: str | None = None


def smtp_configured(app) -> bool:
    user = (app.config.get("MAIL_USERNAME") or "").strip()
    pwd = (app.config.get("MAIL_PASSWORD") or "").strip()
    return user not in ("", "your-email@gmail.com") and pwd not in ("", "your-app-password")


def resend_configured(app) -> bool:
    return bool((app.config.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY", "")).strip())


def send_html_email(app, *, to_email: str, subject: str, html: str) -> bool:
    """Try Gmail SMTP, then Resend API. Returns True if delivered."""
    global last_send_error
    last_send_error = None

    if smtp_configured(app):
        if _send_via_gmail_smtp(app, to_email=to_email, subject=subject, html=html):
            return True
        logger.warning("Gmail SMTP failed for %s; trying Resend if configured.", to_email)

    if resend_configured(app):
        return _send_via_resend(app, to_email=to_email, subject=subject, html=html)

    if smtp_configured(app) and os.environ.get("RENDER", "").strip():
        logger.error(
            "Render blocks Gmail SMTP. Add RESEND_API_KEY to environment "
            "(free at resend.com) for email on the live site."
        )
    return False


def _send_via_gmail_smtp(app, *, to_email: str, subject: str, html: str) -> bool:
    username = app.config["MAIL_USERNAME"].strip()
    password = app.config["MAIL_PASSWORD"].strip()
    timeout = int(app.config.get("MAIL_TIMEOUT") or 8)
    server_host = (app.config.get("MAIL_SERVER") or "smtp.gmail.com").strip()
    port = int(app.config.get("MAIL_PORT") or 587)
    use_tls = bool(app.config.get("MAIL_USE_TLS", True))

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Sports & Outdoors <{username}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    attempts = [(server_host, port, use_tls)]
    if port != 465:
        attempts.append((server_host, 465, False))

    last_error = None
    for host, try_port, try_tls in attempts:
        try:
            if try_port == 465:
                with smtplib.SMTP_SSL(host, try_port, timeout=timeout) as smtp:
                    smtp.login(username, password)
                    smtp.sendmail(username, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(host, try_port, timeout=timeout) as smtp:
                    smtp.ehlo()
                    if try_tls:
                        smtp.starttls()
                        smtp.ehlo()
                    smtp.login(username, password)
                    smtp.sendmail(username, [to_email], msg.as_string())
            logger.info("Gmail SMTP sent to %s via %s:%s", to_email, host, try_port)
            return True
        except Exception as exc:
            last_error = exc
            logger.warning("SMTP %s:%s failed: %s", host, try_port, exc)

    if last_error:
        logger.error("All Gmail SMTP attempts failed for %s: %s", to_email, last_error)
    return False


def _send_via_resend(app, *, to_email: str, subject: str, html: str) -> bool:
    global last_send_error
    api_key = (app.config.get("RESEND_API_KEY") or os.environ.get("RESEND_API_KEY", "")).strip()
    from_addr = (
        app.config.get("RESEND_FROM")
        or os.environ.get("RESEND_FROM")
        or "Sports & Outdoors <onboarding@resend.dev>"
    ).strip()
    reply_to = (app.config.get("MAIL_USERNAME") or "").strip()

    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if reply_to and "@" in reply_to:
        payload["reply_to"] = reply_to

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            logger.info("Resend email sent to %s", to_email)
            last_send_error = None
            return True
        last_send_error = resp.text[:500]
        logger.error("Resend failed (%s): %s", resp.status_code, last_send_error)
        return False
    except requests.RequestException as exc:
        last_send_error = str(exc)
        logger.exception("Resend request error: %s", exc)
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
    return (
        "<!DOCTYPE html><html><body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;'>"
        f"<div style='background:{accent};color:#fff;padding:20px;text-align:center;border-radius:10px 10px 0 0;'>"
        f"<h1 style='margin:0;font-size:22px;'>{title}</h1></div>"
        "<div style='background:#f8f9fa;padding:30px;border-radius:0 0 10px 10px;'>"
        f"<h2 style='color:#333;'>{heading}</h2><p>{body}</p>"
        "<div style='text-align:center;margin:24px 0;background:#fff;border:1px solid #ddd;border-radius:8px;padding:20px;'>"
        f"<div style='font-size:32px;letter-spacing:8px;font-weight:bold;color:{accent};'>{otp_code}</div>"
        "</div>"
        f"<p style='color:#666;font-size:14px;'><a href='{action_link}'>{action_link}</a></p>"
        "<p style='color:#666;font-size:14px;'><strong>Expires in 10 minutes.</strong></p>"
        "</div></body></html>"
    )
