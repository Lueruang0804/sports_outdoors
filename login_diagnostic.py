#!/usr/bin/env python3
"""
Login Diagnostic Script
Comprehensive check of login system
"""

from app import app, db
from database import User
from werkzeug.security import check_password_hash

def run_diagnostic():
    """Run comprehensive login diagnostic"""
    print("🔍 Login System Diagnostic")
    print("=" * 50)
    
    with app.app_context():
        # Check database connection
        try:
            user_count = User.query.count()
            print(f"✅ Database connection: OK ({user_count} users)")
        except Exception as e:
            print(f"❌ Database connection: FAILED - {e}")
            return
        
        # Check all users
        users = User.query.all()
        print(f"\n👥 User Analysis:")
        print("-" * 30)
        
        login_ready = 0
        for user in users:
            can_login = user.is_approved and (user.user_type == 'admin' or user.is_verified)
            if can_login:
                login_ready += 1
            
            status = "✅ READY" if can_login else "❌ BLOCKED"
            print(f"{user.email:<30} {status}")
            
            if not can_login:
                if not user.is_approved:
                    print(f"  └─ Reason: Not approved by admin")
                elif user.user_type != 'admin' and not user.is_verified:
                    print(f"  └─ Reason: Email not verified")
        
        print(f"\n📊 Summary:")
        print(f"Total users: {len(users)}")
        print(f"Login ready: {login_ready}")
        print(f"Blocked: {len(users) - login_ready}")
        
        # Test specific users
        print(f"\n🧪 Testing Specific Users:")
        print("-" * 30)
        
        test_users = [
            ("admin@sportsandoutdoors.com", "admin123"),
            ("axbninja23lueruang@gmail.com", "test123"),  # You'll need to enter the actual password
        ]
        
        for email, test_password in test_users:
            user = User.query.filter_by(email=email).first()
            if user:
                print(f"\n👤 Testing: {email}")
                print(f"  Type: {user.user_type}")
                print(f"  Approved: {user.is_approved}")
                print(f"  Verified: {user.is_verified}")
                
                # Test password (you'll need to know the actual password)
                if check_password_hash(user.password_hash, test_password):
                    print(f"  Password: ✅ CORRECT")
                else:
                    print(f"  Password: ❌ INCORRECT (tried: {test_password})")
                    print(f"  💡 You need to enter the correct password for this user")
        
        print(f"\n💡 Troubleshooting Tips:")
        print("1. Make sure you're using the correct email and password")
        print("2. Check that the user is both approved AND verified")
        print("3. Try logging in with admin account first: admin@sportsandoutdoors.com / admin123")
        print("4. If still having issues, check the server console for error messages")

if __name__ == '__main__':
    run_diagnostic()
