"""
Email keys used on Render when Environment variables are not set.
Prefer setting BREVO_API_KEY (xkeysib-) in Render Dashboard for any recipient.
"""

# Brevo API key (xkeysib-...) — add here after creating at app.brevo.com/settings/keys/api
BREVO_API_KEY = ""

# Brevo SMTP key (xsmtpsib-...) — does not work on Render (SMTP blocked); local dev only
BREVO_SMTP_KEY = ""

RESEND_API_KEY = "re_AVJUhuRX_AqEhmyvKoPQEkK4kxebsnpUi"
RESEND_FROM = "Sports & Outdoors <onboarding@resend.dev>"
