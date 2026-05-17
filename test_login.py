#!/usr/bin/env python3
"""
Login Test Script
This script will help you test login functionality
"""

from app import app, db
from database import User
from werkzeug.security import check_password_hash

def test_login(email, password):
    """Test login for a specific user"""
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"❌ User not found: {email}")
            return False
        
        print(f"👤 User found: {user.email}")
        print(f"📧 Email: {user.email}")
        print(f"👤 Name: {user.first_name} {user.last_name}")
        print(f"🔑 Type: {user.user_type}")
        print(f"✅ Approved: {user.is_approved}")
        print(f"📧 Verified: {user.is_verified}")
        
        # Check password
        if check_password_hash(user.password_hash, password):
            print("🔐 Password: CORRECT")
        else:
            print("🔐 Password: INCORRECT")
            return False
        
        # Check login requirements
        if not user.is_approved:
            print("❌ Login blocked: Account not approved by admin")
            return False
        
        if user.user_type != 'admin' and not user.is_verified:
            print("❌ Login blocked: Email not verified")
            return False
        
        print("✅ All login requirements met!")
        print("🎉 User can login successfully!")
        return True

def list_all_users():
    """List all users with their login status"""
    with app.app_context():
        users = User.query.all()
        print("\n👥 All Users Login Status:")
        print("=" * 100)
        print(f"{'ID':<5} {'Email':<30} {'Name':<20} {'Type':<10} {'Approved':<10} {'Verified':<10} {'Can Login':<10}")
        print("-" * 100)
        
        for user in users:
            name = user.first_name + ' ' + user.last_name
            can_login = 'YES' if (user.is_approved and (user.user_type == 'admin' or user.is_verified)) else 'NO'
            print(f"{user.id:<5} {user.email:<30} {name:<20} {user.user_type:<10} {str(user.is_approved):<10} {str(user.is_verified):<10} {can_login:<10}")

def main():
    """Main test function"""
    print("🧪 Login Test Script")
    print("=" * 30)
    
    while True:
        print("\nOptions:")
        print("1. Test login for specific user")
        print("2. List all users")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == '1':
            email = input("Enter email address: ").strip()
            password = input("Enter password: ").strip()
            print("\n" + "="*50)
            test_login(email, password)
            print("="*50)
            
        elif choice == '2':
            list_all_users()
            
        elif choice == '3':
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == '__main__':
    main()
