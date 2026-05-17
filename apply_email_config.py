#!/usr/bin/env python3
"""
Apply Email Configuration for Automatic OTP Verification
"""

import re

def apply_email_config():
    """Apply email configuration from email_config.txt"""
    
    try:
        # Read configuration file
        with open('email_config.txt', 'r') as f:
            config_content = f.read()
        
        # Extract email and password
        email_match = re.search(r'EMAIL_ADDRESS = (.+)', config_content)
        password_match = re.search(r'APP_PASSWORD = (.+)', config_content)
        
        if not email_match or not password_match:
            print("❌ Error reading email_config.txt")
            print("Please make sure the file has EMAIL_ADDRESS and APP_PASSWORD")
            return False
        
        email = email_match.group(1).strip()
        app_password = password_match.group(1).strip()
        
        if app_password == 'YOUR_16_CHARACTER_APP_PASSWORD_HERE':
            print("❌ Please update email_config.txt with your actual Gmail App Password")
            print("1. Open email_config.txt")
            print("2. Replace YOUR_16_CHARACTER_APP_PASSWORD_HERE with your actual app password")
            print("3. Run this script again")
            return False
        
        if len(app_password.replace(' ', '')) != 16:
            print("❌ App password must be 16 characters long")
            print(f"Current length: {len(app_password.replace(' ', ''))}")
            return False
        
        # Clean password (remove spaces)
        app_password = app_password.replace(' ', '')
        
        print(f"📧 Email: {email}")
        print(f"🔑 App Password: {'*' * 16}")
        
        # Update app.py
        with open('app.py', 'r') as f:
            app_content = f.read()
        
        # Replace email configuration
        app_content = app_content.replace(
            "app.config['MAIL_USERNAME'] = 'your-email@gmail.com'",
            f"app.config['MAIL_USERNAME'] = '{email}'"
        )
        app_content = app_content.replace(
            "app.config['MAIL_PASSWORD'] = 'your-app-password'",
            f"app.config['MAIL_PASSWORD'] = '{app_password}'"
        )
        
        with open('app.py', 'w') as f:
            f.write(app_content)
        
        print("✅ Email configuration applied successfully!")
        print("🔄 Please restart your server to apply changes")
        print()
        print("🚀 Automatic OTP Verification is now set up!")
        print("When you register a new account:")
        print("1. Fill out registration form")
        print("2. Submit the form")
        print("3. Check your email inbox immediately")
        print("4. Click the verification link in the email")
        print("5. You can then log in!")
        
        return True
        
    except FileNotFoundError:
        print("❌ email_config.txt not found")
        print("Please create the configuration file first")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    print("🔧 Applying Email Configuration...")
    apply_email_config()
