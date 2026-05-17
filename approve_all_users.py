#!/usr/bin/env python3
"""
Approve All Users Script
This script will approve all pending users for login
"""

from app import app, db
from database import User

def approve_all_users():
    """Approve all users for login"""
    with app.app_context():
        # Get all unapproved users
        unapproved_users = User.query.filter_by(is_approved=False).all()
        
        if not unapproved_users:
            print("✅ All users are already approved!")
            return
        
        print(f"👥 Found {len(unapproved_users)} unapproved users:")
        print("-" * 50)
        
        for user in unapproved_users:
            print(f"📧 {user.email} ({user.first_name} {user.last_name}) - {user.user_type}")
        
        # Approve all users
        for user in unapproved_users:
            user.is_approved = True
        
        db.session.commit()
        
        print(f"\n✅ Successfully approved {len(unapproved_users)} users!")
        print("🎉 All users can now login!")

def list_user_status():
    """List current status of all users"""
    with app.app_context():
        users = User.query.all()
        print("\n👥 Current User Status:")
        print("=" * 80)
        print(f"{'Email':<30} {'Name':<20} {'Type':<10} {'Approved':<10} {'Can Login':<10}")
        print("-" * 80)
        
        for user in users:
            name = user.first_name + ' ' + user.last_name
            can_login = 'YES' if user.is_approved else 'NO'
            print(f"{user.email:<30} {name:<20} {user.user_type:<10} {str(user.is_approved):<10} {can_login:<10}")

if __name__ == '__main__':
    print("🚀 User Approval System")
    print("=" * 30)
    
    while True:
        print("\nOptions:")
        print("1. Approve all pending users")
        print("2. List user status")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == '1':
            approve_all_users()
            
        elif choice == '2':
            list_user_status()
            
        elif choice == '3':
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice. Please try again.")
