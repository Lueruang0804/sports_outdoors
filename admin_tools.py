#!/usr/bin/env python3
"""
Admin Tools for Testing
Use this script to manually manage users for testing purposes
"""

from app import app, db
from database import User, EmailVerification
from werkzeug.security import generate_password_hash

def create_admin_user():
    """Create an admin user for testing"""
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(email='admin@sportsandoutdoors.com').first()
        if admin:
            print("✅ Admin user already exists")
            return admin
        
        # Create admin user
        admin = User(
            email='admin@sportsandoutdoors.com',
            password_hash=generate_password_hash('admin123'),
            first_name='Admin',
            last_name='User',
            contact_number='1234567890',
            address_region='NCR',
            address_province='Metro Manila',
            address_city='Quezon City',
            address_barangay='Diliman',
            user_type='admin',
            is_verified=True,
            is_approved=True
        )
        
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user created successfully!")
        print("📧 Email: admin@sportsandoutdoors.com")
        print("🔑 Password: admin123")
        return admin

def list_users():
    """List all users in the system"""
    with app.app_context():
        users = User.query.all()
        print("\n👥 All Users in System:")
        print("=" * 80)
        print(f"{'ID':<5} {'Email':<30} {'Name':<20} {'Type':<10} {'Verified':<10} {'Approved':<10}")
        print("-" * 80)
        
        for user in users:
            print(f"{user.id:<5} {user.email:<30} {user.first_name + ' ' + user.last_name:<20} {user.user_type:<10} {str(user.is_verified):<10} {str(user.is_approved):<10}")
        
        print(f"\n📊 Total Users: {len(users)}")

def approve_user(user_id):
    """Approve a user by ID"""
    with app.app_context():
        user = User.query.get(user_id)
        if user:
            user.is_approved = True
            db.session.commit()
            print(f"✅ User {user.email} has been approved!")
        else:
            print(f"❌ User with ID {user_id} not found")

def verify_user(user_id):
    """Manually verify a user by ID"""
    with app.app_context():
        user = User.query.get(user_id)
        if user:
            user.is_verified = True
            db.session.commit()
            print(f"✅ User {user.email} has been verified!")
        else:
            print(f"❌ User with ID {user_id} not found")

def approve_all_pending():
    """Approve all pending users"""
    with app.app_context():
        pending_users = User.query.filter_by(is_approved=False).all()
        for user in pending_users:
            user.is_approved = True
        db.session.commit()
        print(f"✅ Approved {len(pending_users)} pending users!")

def verify_all_unverified():
    """Verify all unverified users"""
    with app.app_context():
        unverified_users = User.query.filter_by(is_verified=False).all()
        for user in unverified_users:
            user.is_verified = True
        db.session.commit()
        print(f"✅ Verified {len(unverified_users)} unverified users!")

def get_verification_links():
    """Get all active verification links"""
    with app.app_context():
        verifications = EmailVerification.query.filter_by(is_used=False).all()
        print("\n🔗 Active Verification Links:")
        print("=" * 100)
        
        for verification in verifications:
            user = User.query.get(verification.user_id)
            if user:
                print(f"User: {user.email} ({user.first_name} {user.last_name})")
                print(f"Link: http://localhost:5000/verify-email/{verification.token}")
                print(f"Expires: {verification.expires_at}")
                print("-" * 100)

def main():
    """Main menu for admin tools"""
    while True:
        print("\n🛠️  Admin Tools Menu")
        print("=" * 30)
        print("1. Create Admin User")
        print("2. List All Users")
        print("3. Approve User by ID")
        print("4. Verify User by ID")
        print("5. Approve All Pending Users")
        print("6. Verify All Unverified Users")
        print("7. Get Verification Links")
        print("8. Exit")
        
        choice = input("\nEnter your choice (1-8): ").strip()
        
        if choice == '1':
            create_admin_user()
        elif choice == '2':
            list_users()
        elif choice == '3':
            user_id = input("Enter user ID to approve: ").strip()
            try:
                approve_user(int(user_id))
            except ValueError:
                print("❌ Invalid user ID")
        elif choice == '4':
            user_id = input("Enter user ID to verify: ").strip()
            try:
                verify_user(int(user_id))
            except ValueError:
                print("❌ Invalid user ID")
        elif choice == '5':
            approve_all_pending()
        elif choice == '6':
            verify_all_unverified()
        elif choice == '7':
            get_verification_links()
        elif choice == '8':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == '__main__':
    print("🚀 Starting Admin Tools...")
    main()
