#!/usr/bin/env python3
"""
Quick Email Configuration Helper
"""

def update_email_config():
    """Update email configuration in app.py"""
    print("📧 Email Configuration Setup")
    print("=" * 40)
    print("To receive verification emails in your real email account:")
    print()
    print("1. Go to https://myaccount.google.com/security")
    print("2. Enable 2-Factor Authentication")
    print("3. Go to 'App passwords' section")
    print("4. Generate a new app password for 'Mail'")
    print("5. Copy the 16-character password")
    print()
    
    email = input("Enter your Gmail address: ").strip()
    app_password = input("Enter your Gmail App Password (16 characters): ").strip().replace(' ', '')
    
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
        
        print("✅ Email configuration updated!")
        print("🔄 Restart your server to apply changes")
        print("📧 You will now receive verification emails!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    update_email_config()
