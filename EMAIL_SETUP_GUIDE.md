# Email Verification Setup Guide

## Overview
This guide will help you set up email verification for your Sports and Outdoors Ecommerce System.

## Email Configuration

### 1. Gmail Setup (Recommended for Development)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"
   - Copy the 16-character password

3. **Update app.py configuration**:
```python
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-16-character-app-password'
```

### 2. Other Email Providers

#### Outlook/Hotmail:
```python
app.config['MAIL_SERVER'] = 'smtp-mail.outlook.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
```

#### Yahoo:
```python
app.config['MAIL_SERVER'] = 'smtp.mail.yahoo.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
```

## Database Migration

Run the migration script to add the EmailVerification table:

```bash
python migrate_email_verification.py
```

## Features

### ✅ What's Included:

1. **Secure Token System**: 
   - 32-character secure tokens
   - 24-hour expiration
   - One-time use tokens

2. **Beautiful Email Templates**:
   - HTML formatted emails
   - Professional design
   - Clear call-to-action buttons

3. **User-Friendly Interface**:
   - Resend verification option
   - Clear error messages
   - Helpful instructions

4. **Security Features**:
   - Token expiration
   - Used token invalidation
   - Email validation

### 🔄 User Flow:

1. **Registration** → User fills out form
2. **Email Sent** → Verification email with secure link
3. **Email Verification** → User clicks link to verify
4. **Account Activated** → User can now login
5. **Resend Option** → If email is lost, user can request new one

### 📧 Email Template Features:

- Professional HTML design
- Mobile-responsive
- Clear verification button
- Fallback text link
- Expiration notice
- Security information

## Testing

### Test the Email Verification:

1. **Register a new account**
2. **Check your email** (including spam folder)
3. **Click the verification link**
4. **Try logging in**

### Test Resend Functionality:

1. **Go to login page**
2. **Click "Resend Email Verification"**
3. **Enter your email**
4. **Check for new verification email**

## Troubleshooting

### Common Issues:

1. **Email not received**:
   - Check spam/junk folder
   - Verify email configuration
   - Check SMTP settings

2. **Verification link expired**:
   - Use "Resend Email Verification" feature
   - Links expire after 24 hours

3. **Database errors**:
   - Run the migration script
   - Check database connection
   - Verify table creation

### Debug Mode:

To debug email issues, add this to your app.py:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Notes

- Tokens are cryptographically secure
- Tokens expire after 24 hours
- Used tokens are invalidated
- No sensitive data in URLs
- Email addresses are validated

## Production Considerations

For production deployment:

1. **Use a dedicated email service** (SendGrid, Mailgun, AWS SES)
2. **Set up proper DNS records** (SPF, DKIM, DMARC)
3. **Monitor email delivery rates**
4. **Set up email templates in your service**
5. **Configure proper error handling**

## Support

If you encounter issues:

1. Check the console logs for errors
2. Verify email configuration
3. Test with a simple email first
4. Check database connectivity
5. Review the migration script output
