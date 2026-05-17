#!/usr/bin/env python3
"""
Test Forgot Password Functionality
"""

from app import app, db
from database import User, EmailVerification
from werkzeug.security import generate_password_hash
import secrets
from datetime import datetime, timedelta

def test_forgot_password():
    """Test the forgot password functionality"""
    with app.app_context():
        print("🧪 Testing Forgot Password Functionality")
        print("=" * 50)
        
        # Test with your email
        test_email = "axbninja23lueruang@gmail.com"
        user = User.query.filter_by(email=test_email).first()
        
        if not user:
            print(f"❌ User not found: {test_email}")
            return
        
        print(f"👤 Testing with: {test_email}")
        
        # Generate reset token (simulating forgot password request)
        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Delete any existing reset tokens
        EmailVerification.query.filter_by(user_id=user.id, is_used=False).delete()
        
        # Create new reset token
        reset_verification = EmailVerification(
            user_id=user.id,
            token=reset_token,
            email=test_email,
            expires_at=expires_at
        )
        
        db.session.add(reset_verification)
        db.session.commit()
        
        # Generate reset link
        reset_link = f"http://localhost:5000/reset-password/{reset_token}"
        
        print(f"✅ Reset token generated successfully!")
        print(f"🔗 Reset Link: {reset_link}")
        print(f"⏰ Expires: {expires_at}")
        print()
        print("💡 Instructions:")
        print("1. Copy the reset link above")
        print("2. Paste it in your browser")
        print("3. Enter your new password")
        print("4. You can then login with the new password")
        
        return reset_link

if __name__ == '__main__':
    test_forgot_password()
