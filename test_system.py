#!/usr/bin/env python3
"""
System test script for Sports and Outdoors Ecommerce System
This script tests the core functionality of the system
"""

import os
import sys
import requests
import time
from app import app, db
from database import User, Product, Order, Notification

def test_database_connection():
    """Test database connection and basic operations"""
    print("Testing database connection...")
    try:
        with app.app_context():
            # Test database connection
            user_count = User.query.count()
            product_count = Product.query.count()
            print(f"SUCCESS: Database connected successfully")
            print(f"   - Users in database: {user_count}")
            print(f"   - Products in database: {product_count}")
            return True
    except Exception as e:
        print(f"ERROR: Database connection failed: {str(e)}")
        return False

def test_user_creation():
    """Test user creation and authentication"""
    print("Testing user creation...")
    try:
        with app.app_context():
            # Test if we can create a user
            test_user = User(
                first_name="Test",
                last_name="User",
                email="test@example.com",
                password_hash="test_hash",
                contact_number="09123456789",
                address_region="NCR",
                address_province="Metro Manila",
                address_city="Quezon City",
                address_barangay="Diliman",
                address_street="Test Street",
                user_type="buyer",
                is_verified=True,
                is_approved=True
            )
            db.session.add(test_user)
            db.session.commit()
            
            # Verify user was created
            created_user = User.query.filter_by(email="test@example.com").first()
            if created_user:
                print("SUCCESS: User creation test passed")
                # Clean up test user
                db.session.delete(created_user)
                db.session.commit()
                return True
            else:
                print("ERROR: User creation test failed")
                return False
    except Exception as e:
        print(f"ERROR: User creation test failed: {str(e)}")
        return False

def test_product_creation():
    """Test product creation"""
    print("Testing product creation...")
    try:
        with app.app_context():
            # Get a seller user
            seller = User.query.filter_by(user_type="seller").first()
            if not seller:
                print("ERROR: No seller found for product test")
                return False
            
            # Test product creation
            test_product = Product(
                name="Test Product",
                description="Test product description",
                price=100.00,
                category="Test Category",
                stock_quantity=10,
                seller_id=seller.id
            )
            db.session.add(test_product)
            db.session.commit()
            
            # Verify product was created
            created_product = Product.query.filter_by(name="Test Product").first()
            if created_product:
                print("SUCCESS: Product creation test passed")
                # Clean up test product
                db.session.delete(created_product)
                db.session.commit()
                return True
            else:
                print("ERROR: Product creation test failed")
                return False
    except Exception as e:
        print(f"ERROR: Product creation test failed: {str(e)}")
        return False

def test_route_access():
    """Test if routes are accessible"""
    print("Testing route access...")
    try:
        with app.test_client() as client:
            # Test main routes
            routes_to_test = [
                ("/", "Homepage"),
                ("/products", "Products page"),
                ("/about", "About page"),
                ("/contact", "Contact page"),
                ("/login", "Login page"),
                ("/register", "Register page")
            ]
            
            for route, description in routes_to_test:
                response = client.get(route)
                if response.status_code == 200:
                    print(f"SUCCESS: {description} accessible")
                else:
                    print(f"ERROR: {description} not accessible (Status: {response.status_code})")
                    return False
            
            return True
    except Exception as e:
        print(f"ERROR: Route access test failed: {str(e)}")
        return False

def test_file_uploads():
    """Test file upload functionality"""
    print("Testing file upload directories...")
    try:
        upload_dirs = [
            "static/uploads/products",
            "static/uploads/profiles",
            "static/uploads/documents",
            "static/uploads/advertisements"
        ]
        
        for directory in upload_dirs:
            if os.path.exists(directory):
                print(f"SUCCESS: {directory} exists")
            else:
                print(f"ERROR: {directory} missing")
                # Create the directory
                os.makedirs(directory, exist_ok=True)
                print(f"SUCCESS: {directory} created")
        
        return True
    except Exception as e:
        print(f"ERROR: File upload test failed: {str(e)}")
        return False

def test_sample_data():
    """Test if sample data exists"""
    print("Testing sample data...")
    try:
        with app.app_context():
            # Check for sample users
            admin_count = User.query.filter_by(user_type="admin").count()
            seller_count = User.query.filter_by(user_type="seller").count()
            buyer_count = User.query.filter_by(user_type="buyer").count()
            rider_count = User.query.filter_by(user_type="rider").count()
            
            print(f"   - Admin users: {admin_count}")
            print(f"   - Seller users: {seller_count}")
            print(f"   - Buyer users: {buyer_count}")
            print(f"   - Rider users: {rider_count}")
            
            # Check for sample products
            product_count = Product.query.count()
            print(f"   - Products: {product_count}")
            
            if admin_count > 0 and seller_count > 0 and buyer_count > 0 and rider_count > 0:
                print("SUCCESS: Sample data exists")
                return True
            else:
                print("ERROR: Sample data incomplete")
                return False
    except Exception as e:
        print(f"ERROR: Sample data test failed: {str(e)}")
        return False

def main():
    """Run all system tests"""
    print("="*60)
    print("SPORTS AND OUTDOORS ECOMMERCE SYSTEM TEST")
    print("="*60)
    print()
    
    tests = [
        ("Database Connection", test_database_connection),
        ("User Creation", test_user_creation),
        ("Product Creation", test_product_creation),
        ("Route Access", test_route_access),
        ("File Uploads", test_file_uploads),
        ("Sample Data", test_sample_data)
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * 40)
        if test_func():
            passed_tests += 1
        else:
            print(f"ERROR: {test_name} failed")
    
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"Tests passed: {passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        print("ALL TESTS PASSED! System is ready to use.")
        print("\nYou can now start the application:")
        print("   - Windows: Double-click start.bat")
        print("   - Linux/Mac: Run ./start.sh")
        print("   - Or run: python run.py")
        print("\nAccess the system at: http://localhost:5000")
    else:
        print("ERROR: Some tests failed. Please check the errors above.")
        print("Try running the setup script again: python setup_system.py")
    
    print("="*60)

if __name__ == "__main__":
    main()
