#!/usr/bin/env python3
"""
Email Setup Helper Script
This script will help you configure email settings for OTP verification
"""

import os
import re

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def setup_email_config():
    """Interactive email setup"""
    print("📧 Email Configuration Setup")
    print("=" * 40)
    print("This will help you configure email settings for OTP verification.")
    print()
    
    # Get email address
    while True:
        email = input("Enter your Gmail address: ").strip()
        if validate_email(email):
            break
        print("❌ Please enter a valid email address")
    
    print()
    print("🔐 Gmail App Password Setup:")
    print("1. Go to https://myaccount.google.com/security")
    print("2. Enable 2-Factor Authentication if not already enabled")
    print("3. Go to 'App passwords' section")
    print("4. Generate a new app password for 'Mail'")
    print("5. Copy the 16-character password (like: abcd efgh ijkl mnop)")
    print()
    
    # Get app password
    while True:
        app_password = input("Enter your Gmail App Password (16 characters): ").strip()
        if len(app_password.replace(' ', '')) == 16:
            app_password = app_password.replace(' ', '')  # Remove spaces
            break
        print("❌ App password should be 16 characters long")
    
    # Update app.py
    try:
        with open('app.py', 'r') as f:
            content = f.read()
        
        # Replace email configuration
        content = content.replace(
            "app.config['MAIL_USERNAME'] = 'your-email@gmail.com'",
            f"app.config['MAIL_USERNAME'] = '{email}'"
        )
        content = content.replace(
            "app.config['MAIL_PASSWORD'] = 'your-app-password'",
            f"app.config['MAIL_PASSWORD'] = '{app_password}'"
        )
        
        with open('app.py', 'w') as f:
            f.write(content)
        
        print("✅ Email configuration updated successfully!")
        print(f"📧 Email: {email}")
        print("🔑 App Password: [HIDDEN]")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating configuration: {e}")
        return False

def test_email_config():
    """Test the email configuration"""
    print("\n🧪 Testing Email Configuration...")
    
    try:
        from app import app, mail
        from flask_mail import Message
        
        with app.app_context():
            msg = Message(
                'Test Email - OTP Verification Setup',
                sender=app.config['MAIL_USERNAME'],
                recipients=[app.config['MAIL_USERNAME']]
            )
            msg.html = '''
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1>✅ Email Setup Successful!</h1>
                </div>
                <div style="background-color: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #333;">Your Email Configuration is Working!</h2>
                    <p>This is a test email from your Sports and Outdoors Ecommerce System.</p>
                    <p>You will now receive:</p>
                    <ul>
                        <li>✅ Email verification links when registering</li>
                        <li>✅ Password reset emails</li>
                        <li>✅ OTP verification codes</li>
                        <li>✅ System notifications</li>
                    </ul>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    <p style="color: #999; font-size: 12px; text-align: center;">
                        © 2024 Sports and Outdoors Ecommerce System. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            '''
            
            mail.send(msg)
            print("✅ Test email sent successfully!")
            print("📬 Please check your inbox and spam folder")
            return True
            
    except Exception as e:
        print(f"❌ Error sending test email: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Make sure 2-Factor Authentication is enabled on your Gmail")
        print("2. Verify you're using the correct App Password")
        print("3. Check your internet connection")
        print("4. Try again or use a different Gmail account")
        return False

def main():
    """Main setup function"""
    print("🚀 Email Setup for OTP Verification")
    print("=" * 50)
    
    # Check current configuration
    try:
        with open('app.py', 'r') as f:
            content = f.read()
        
        if 'your-email@gmail.com' in content:
            print("⚠️  Email configuration needs to be set up")
            setup = input("Would you like to set up email now? (y/n): ").strip().lower()
            
            if setup == 'y':
                if setup_email_config():
                    test = input("Would you like to test the email configuration? (y/n): ").strip().lower()
                    if test == 'y':
                        test_email_config()
                else:
                    print("❌ Setup failed. Please try again.")
            else:
                print("📝 You can set up email later by running this script again")
        else:
            print("✅ Email configuration appears to be set up")
            test = input("Would you like to test the email configuration? (y/n): ").strip().lower()
            if test == 'y':
                test_email_config()
                
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")

if __name__ == '__main__':
    main()
