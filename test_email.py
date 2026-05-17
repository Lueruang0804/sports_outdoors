#!/usr/bin/env python3
"""
Email Configuration Test Script
Run this to test if your email setup is working correctly
"""

from flask import Flask
from flask_mail import Mail, Message
import os

# Create Flask app
app = Flask(__name__)

# Email configuration - UPDATE THESE VALUES
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # CHANGE THIS
app.config['MAIL_PASSWORD'] = 'your-app-password'     # CHANGE THIS

# Initialize Mail
mail = Mail(app)

def test_email():
    """Test email sending functionality"""
    try:
        with app.app_context():
            # Create test message
            msg = Message(
                'Test Email - Sports and Outdoors Ecommerce',
                sender=app.config['MAIL_USERNAME'],
                recipients=[app.config['MAIL_USERNAME']]  # Send to yourself
            )
            msg.html = '''
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1>✅ Email Test Successful!</h1>
                </div>
                <div style="background-color: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #333;">Your Email Configuration is Working!</h2>
                    <p>This is a test email from your Sports and Outdoors Ecommerce System.</p>
                    <p>If you received this email, your email configuration is set up correctly and you can now:</p>
                    <ul>
                        <li>Receive email verification links</li>
                        <li>Receive password reset emails</li>
                        <li>Get notifications from the system</li>
                    </ul>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    <p style="color: #999; font-size: 12px; text-align: center;">
                        © 2024 Sports and Outdoors Ecommerce System. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            '''
            
            # Send email
            mail.send(msg)
            print("✅ SUCCESS: Test email sent successfully!")
            print(f"📧 Email sent to: {app.config['MAIL_USERNAME']}")
            print("📬 Please check your inbox and spam folder")
            return True
            
    except Exception as e:
        print("❌ ERROR: Failed to send test email")
        print(f"🔍 Error details: {e}")
        print("\n🔧 Troubleshooting steps:")
        print("1. Make sure you've updated MAIL_USERNAME and MAIL_PASSWORD in this file")
        print("2. Check the GMAIL_SETUP_GUIDE.md for detailed setup instructions")
        print("3. Ensure you're using a Gmail App Password (not your regular password)")
        print("4. Verify that 2-Factor Authentication is enabled on your Gmail account")
        return False

if __name__ == '__main__':
    print("🧪 Testing Email Configuration...")
    print("=" * 50)
    
    # Check if credentials are still placeholder values
    if app.config['MAIL_USERNAME'] == 'your-email@gmail.com':
        print("⚠️  WARNING: You haven't updated the email credentials yet!")
        print("📝 Please edit this file and update:")
        print("   - MAIL_USERNAME: Your actual Gmail address")
        print("   - MAIL_PASSWORD: Your Gmail App Password")
        print("\n📖 See GMAIL_SETUP_GUIDE.md for detailed instructions")
        exit(1)
    
    if app.config['MAIL_PASSWORD'] == 'your-app-password':
        print("⚠️  WARNING: You haven't updated the email password yet!")
        print("📝 Please edit this file and update MAIL_PASSWORD with your Gmail App Password")
        print("\n📖 See GMAIL_SETUP_GUIDE.md for detailed instructions")
        exit(1)
    
    # Test email sending
    success = test_email()
    
    if success:
        print("\n🎉 Email configuration is working correctly!")
        print("🚀 You can now use the registration and forgot password features")
    else:
        print("\n💡 Need help? Check GMAIL_SETUP_GUIDE.md for troubleshooting")
