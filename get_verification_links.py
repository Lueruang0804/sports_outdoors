#!/usr/bin/env python3
"""
Get Verification Links Script
This script will show you all active verification links
"""

from app import app, db
from database import EmailVerification, User

def get_verification_links():
    """Get all active verification links"""
    with app.app_context():
        verifications = EmailVerification.query.filter_by(is_used=False).all()
        
        if not verifications:
            print("❌ No active verification links found")
            return
        
        print("\n🔗 Active Verification Links:")
        print("=" * 100)
        
        for verification in verifications:
            user = User.query.get(verification.user_id)
            if user:
                print(f"👤 User: {user.email} ({user.first_name} {user.last_name})")
                print(f"🔗 Verification Link: http://localhost:5000/verify-email/{verification.token}")
                print(f"⏰ Expires: {verification.expires_at}")
                print(f"📧 Email: {verification.email}")
                print("-" * 100)
        
        print(f"\n📊 Total Active Links: {len(verifications)}")
        print("\n💡 Instructions:")
        print("1. Copy any verification link above")
        print("2. Paste it in your browser")
        print("3. This will verify the user's email")
        print("4. After verification, the user can log in")

if __name__ == '__main__':
    print("🔍 Getting Verification Links...")
    get_verification_links()
