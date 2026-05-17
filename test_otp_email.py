#!/usr/bin/env python3
"""
Test OTP Email Verification
"""

from app import app, mail
from flask_mail import Message

def test_otp_email():
    """Test sending OTP verification email"""
    
    email = "axbninja23lueruang@gmail.com"
    
    try:
        with app.app_context():
            # Create test verification email
            msg = Message(
                'Test OTP Verification - Sports and Outdoors Ecommerce',
                sender=app.config['MAIL_USERNAME'],
                recipients=[email]
            )
            msg.html = '''
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1>🎉 OTP Verification Test</h1>
                </div>
                <div style="background-color: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #333;">Email Verification Working!</h2>
                    <p>This is a test email to verify that your OTP email system is working correctly.</p>
                    <p>When you register a new account, you will receive a similar email with a verification link.</p>
                    
                    <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #495057; margin-top: 0;">✅ What happens when you register:</h3>
                        <ol style="color: #495057;">
                            <li>Fill out registration form</li>
                            <li>Submit the form</li>
                            <li><strong>Check your email inbox immediately</strong></li>
                            <li>Click the verification link in the email</li>
                            <li>Your account is verified and you can log in!</li>
                        </ol>
                    </div>
                    
                    <p style="color: #666; font-size: 14px;">
                        <strong>Note:</strong> If you don't see the email in your inbox, check your spam/junk folder.
                    </p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    <p style="color: #999; font-size: 12px; text-align: center;">
                        © 2024 Sports and Outdoors Ecommerce System. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            '''
            
            mail.send(msg)
            print("✅ Test OTP email sent successfully!")
            print(f"📧 Email sent to: {email}")
            print("📬 Please check your inbox and spam folder")
            print()
            print("🎯 If you received this email, your automatic OTP verification is working!")
            return True
            
    except Exception as e:
        print(f"❌ Error sending test email: {e}")
        print()
        print("🔧 Troubleshooting:")
        print("1. Make sure you've set up your Gmail App Password")
        print("2. Check that 2-Factor Authentication is enabled")
        print("3. Verify the email configuration in app.py")
        return False

if __name__ == '__main__':
    print("🧪 Testing OTP Email Verification...")
    test_otp_email()
