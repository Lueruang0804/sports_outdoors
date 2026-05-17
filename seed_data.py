#!/usr/bin/env python3
"""
Sample data seeding script for Sports and Outdoors Ecommerce System
Run this script to populate the database with sample data for testing
"""

from app import app, db
from database import User, Product, Advertisement, Notification
from werkzeug.security import generate_password_hash
import json
from datetime import datetime, timedelta

def create_sample_data():
    """Create sample data for testing the system"""
    
    with app.app_context():
        # Create database tables
        db.create_all()
        
        print("Creating sample data...")
        
        # Create admin user
        admin = User(
            first_name="Admin",
            last_name="User",
            email="admin@sportsandoutdoors.com",
            password_hash=generate_password_hash("admin123"),
            contact_number="09123456789",
            user_type="admin",
            is_verified=True,
            is_approved=True,
            address_region="NCR",
            address_province="Metro Manila",
            address_city="Quezon City",
            address_barangay="Diliman"
        )
        db.session.add(admin)
        
        # Create sample seller
        seller = User(
            first_name="John",
            last_name="Smith",
            email="seller@sportsandoutdoors.com",
            password_hash=generate_password_hash("seller123"),
            contact_number="09123456788",
            user_type="seller",
            is_verified=True,
            is_approved=True,
            address_region="NCR",
            address_province="Metro Manila",
            address_city="Makati City",
            address_barangay="Ayala",
            product_categories=json.dumps([
                "Fitness Equipment",
                "Sports Apparel",
                "Cycling & Bikes"
            ])
        )
        db.session.add(seller)
        
        # Create sample buyer
        buyer = User(
            first_name="Jane",
            last_name="Doe",
            email="buyer@sportsandoutdoors.com",
            password_hash=generate_password_hash("buyer123"),
            contact_number="09123456787",
            user_type="buyer",
            is_verified=True,
            is_approved=True,
            address_region="NCR",
            address_province="Metro Manila",
            address_city="Taguig City",
            address_barangay="Bonifacio Global City"
        )
        db.session.add(buyer)
        
        # Create sample rider
        rider = User(
            first_name="Mike",
            last_name="Johnson",
            email="rider@sportsandoutdoors.com",
            password_hash=generate_password_hash("rider123"),
            contact_number="09123456786",
            user_type="rider",
            is_verified=True,
            is_approved=True,
            address_region="NCR",
            address_province="Metro Manila",
            address_city="Pasig City",
            address_barangay="Ortigas"
        )
        db.session.add(rider)
        
        db.session.commit()
        print("Sample users created")
        
        # Create sample products
        products_data = [
            {
                "name": "Professional Dumbbell Set",
                "description": "High-quality rubber-coated dumbbells perfect for home gym workouts. Available in various weights.",
                "price": 2500.00,
                "category": "Fitness Equipment",
                "stock_quantity": 50
            },
            {
                "name": "Mountain Bike Helmet",
                "description": "Lightweight and durable helmet with advanced ventilation system for comfortable cycling.",
                "price": 1200.00,
                "category": "Cycling & Bikes",
                "stock_quantity": 30
            },
            {
                "name": "Running Shoes",
                "description": "Comfortable running shoes with excellent cushioning and breathable material.",
                "price": 3500.00,
                "category": "Sports Apparel",
                "stock_quantity": 25
            },
            {
                "name": "Camping Tent 4-Person",
                "description": "Spacious 4-person tent perfect for family camping trips. Waterproof and easy to set up.",
                "price": 4500.00,
                "category": "Camping & Hiking Gear",
                "stock_quantity": 15
            },
            {
                "name": "Basketball",
                "description": "Official size basketball with excellent grip and durability for indoor and outdoor play.",
                "price": 800.00,
                "category": "Team Sports Equipment",
                "stock_quantity": 40
            },
            {
                "name": "Swimming Goggles",
                "description": "Anti-fog swimming goggles with UV protection and comfortable fit.",
                "price": 600.00,
                "category": "Water Sports",
                "stock_quantity": 35
            }
        ]
        
        for product_data in products_data:
            product = Product(
                name=product_data["name"],
                description=product_data["description"],
                price=product_data["price"],
                category=product_data["category"],
                stock_quantity=product_data["stock_quantity"],
                seller_id=seller.id,
                status="active"
            )
            db.session.add(product)
        
        db.session.commit()
        print("Sample products created")
        
        # Create sample advertisements
        advertisements_data = [
            {
                "title": "Summer Sports Sale",
                "description": "Get up to 20% off on all summer sports equipment! Perfect time to gear up for the season.",
                "discount_percentage": 20,
                "promo_code": "SUMMER25",
                "expires_at": datetime.now() + timedelta(days=30),
            },
            {
                "title": "New Year Fitness Challenge",
                "description": "Start your fitness journey with our premium equipment. Special discounts on fitness gear!",
                "discount_percentage": 25,
                "promo_code": "FITNESS25",
                "expires_at": datetime.now() + timedelta(days=45),
            },
        ]

        for ad_data in advertisements_data:
            advertisement = Advertisement(
                title=ad_data["title"],
                description=ad_data["description"],
                discount_percentage=ad_data["discount_percentage"],
                promo_code=(ad_data.get("promo_code") or "").strip().upper() or None,
                expires_at=ad_data["expires_at"],
                is_active=True,
            )
            db.session.add(advertisement)
        
        db.session.commit()
        print("Sample advertisements created")
        
        # Create sample notifications
        notifications_data = [
            {
                "user_id": buyer.id,
                "title": "Welcome to Sports and Outdoors!",
                "message": "Thank you for joining our platform. Start exploring our amazing sports and outdoor equipment!",
                "notification_type": "welcome"
            },
            {
                "user_id": seller.id,
                "title": "Account Approved",
                "message": "Your seller account has been approved! You can now start listing your products.",
                "notification_type": "account_approved"
            }
        ]
        
        for notif_data in notifications_data:
            notification = Notification(
                user_id=notif_data["user_id"],
                title=notif_data["title"],
                message=notif_data["message"],
                notification_type=notif_data["notification_type"]
            )
            db.session.add(notification)
        
        db.session.commit()
        print("Sample notifications created")
        
        print("\n" + "="*50)
        print("SAMPLE DATA CREATED SUCCESSFULLY!")
        print("="*50)
        print("\nTest Accounts:")
        print("Admin: admin@sportsandoutdoors.com / admin123")
        print("Seller: seller@sportsandoutdoors.com / seller123")
        print("Buyer: buyer@sportsandoutdoors.com / buyer123")
        print("Rider: rider@sportsandoutdoors.com / rider123")
        print("\nYou can now run the application and test all features!")
        print("="*50)

if __name__ == "__main__":
    create_sample_data()
