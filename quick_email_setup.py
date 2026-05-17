#!/usr/bin/env python3
"""
Quick Email Setup for Automatic OTP Verification
"""

def setup_automatic_otp():
    """Set up email for automatic OTP verification"""
    
    # Your email configuration
    email = "axbninja23lueruang@gmail.com"
    
    print("📧 Setting up automatic OTP verification...")
    print(f"📧 Email: {email}")
    print()
    print("🔐 To complete setup, you need your Gmail App Password:")
    print("1. Go to: https://myaccount.google.com/security")
    print("2. Enable 2-Factor Authentication")
    print("3. Go to 'App passwords' section")
    print("4. Generate app password for 'Mail'")
    print("5. Copy the 16-character password")
    print()
    
    app_password = input("Enter your Gmail App Password (16 characters): ").strip().replace(' ', '')
    
    if len(app_password) != 16:
        print("❌ App password must be 16 characters long")
        return False
    
    try:
        # Read current app.py
        with open('app.py', 'r') as f:
            content = f.read()
        
        # Update email configuration
        content = content.replace(
            "app.config['MAIL_USERNAME'] = 'your-email@gmail.com'",
            f"app.config['MAIL_USERNAME'] = '{email}'"
        )
        content = content.replace(
            "app.config['MAIL_PASSWORD'] = 'your-app-password'",
            f"app.config['MAIL_PASSWORD'] = '{app_password}'"
        )
        
        # Write updated content
        with open('app.py', 'w') as f:
            f.write(content)
        
        print("✅ Email configuration updated successfully!")
        print("🔄 Please restart your server to apply changes")
        print()
        print("🚀 Now when you register:")
        print("1. Fill out registration form")
        print("2. Submit the form")
        print("3. Check your email inbox immediately")
        print("4. Click the verification link in the email")
        print("5. You can then log in!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating configuration: {e}")
        return False

if __name__ == '__main__':
    setup_automatic_otp()
