#!/usr/bin/env python3
"""
Test Advertisement System
"""

from app import app, db
from database import User, Product, SellerAdvertisement
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

def create_test_data():
    """Create test data for advertisement system"""
    with app.app_context():
        print("🧪 Creating test data for advertisement system...")
        
        # Create test seller if not exists
        seller = User.query.filter_by(email='test_seller@example.com').first()
        if not seller:
            seller = User(
                email='test_seller@example.com',
                password_hash=generate_password_hash('password123'),
                first_name='Test',
                last_name='Seller',
                contact_number='1234567890',
                address_region='NCR',
                address_province='Metro Manila',
                address_city='Quezon City',
                address_barangay='Diliman',
                user_type='seller',
                is_verified=True,
                is_approved=True
            )
            db.session.add(seller)
            db.session.flush()
            print(f"✅ Created test seller: {seller.email}")
        
        # Create test product if not exists
        product = Product.query.filter_by(seller_id=seller.id).first()
        if not product:
            product = Product(
                name='Test Camping Tent',
                description='A high-quality camping tent perfect for outdoor adventures.',
                price=2500.00,
                category='Camping & Hiking Gear',
                stock_quantity=10,
                seller_id=seller.id,
                status='active'
            )
            db.session.add(product)
            db.session.flush()
            print(f"✅ Created test product: {product.name}")
        
        # Create test advertisement if not exists
        existing_ad = SellerAdvertisement.query.filter_by(seller_id=seller.id).first()
        if not existing_ad:
            now = datetime.utcnow()
            expires_at = now + timedelta(days=7)
            
            advertisement = SellerAdvertisement(
                seller_id=seller.id,
                product_id=product.id,
                title='Summer Sale - 20% Off Camping Tents!',
                description='Get amazing discounts on our premium camping tents. Perfect for your next outdoor adventure!',
                discount_percentage=20,
                original_price=2500.00,
                discounted_price=2000.00,
                promo_message='Limited time offer! Don\'t miss out on this amazing deal!',
                starts_at=now,
                expires_at=expires_at,
                is_active=True,
                is_approved=True
            )
            db.session.add(advertisement)
            db.session.commit()
            print(f"✅ Created test advertisement: {advertisement.title}")
        
        print("\n📊 Test Data Summary:")
        print(f"Seller: {seller.email}")
        print(f"Product: {product.name} - ₱{product.price}")
        print(f"Advertisement: {existing_ad.title if existing_ad else advertisement.title}")
        print(f"Discount: {existing_ad.discount_percentage if existing_ad else advertisement.discount_percentage}%")
        print(f"Discounted Price: ₱{existing_ad.discounted_price if existing_ad else advertisement.discounted_price}")

def test_advertisement_flow():
    """Test the complete advertisement flow"""
    with app.app_context():
        print("\n🧪 Testing Advertisement Flow...")
        
        # Get active advertisements
        now = datetime.utcnow()
        active_ads = SellerAdvertisement.query.filter(
            SellerAdvertisement.is_active == True,
            SellerAdvertisement.is_approved == True,
            SellerAdvertisement.starts_at <= now,
            SellerAdvertisement.expires_at > now
        ).all()
        
        print(f"📈 Found {len(active_ads)} active advertisements")
        
        for ad in active_ads:
            print(f"\n📢 Advertisement: {ad.title}")
            print(f"   Product: {ad.product.name}")
            print(f"   Discount: {ad.discount_percentage}%")
            print(f"   Original Price: ₱{ad.original_price}")
            print(f"   Discounted Price: ₱{ad.discounted_price}")
            print(f"   Expires: {ad.expires_at}")
            print(f"   Status: {'Active' if ad.is_active else 'Inactive'}")
            print(f"   Approved: {'Yes' if ad.is_approved else 'No'}")

if __name__ == '__main__':
    create_test_data()
    test_advertisement_flow()
    print("\n🎉 Advertisement system test completed!")
    print("\n💡 Next steps:")
    print("1. Login as seller to create advertisements")
    print("2. Login as admin to approve advertisements")
    print("3. Visit homepage to see advertisements")
    print("4. Click on advertisements to test discount flow")
