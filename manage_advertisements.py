#!/usr/bin/env python3
"""
Advertisement Management Script
"""

from app import app, db
from database import SellerAdvertisement, User, Product
from datetime import datetime, timedelta

def list_all_advertisements():
    """List all advertisements with their status"""
    with app.app_context():
        print("📢 All Seller Advertisements")
        print("=" * 60)
        
        ads = db.session.query(SellerAdvertisement, User, Product).join(
            User, SellerAdvertisement.seller_id == User.id
        ).join(
            Product, SellerAdvertisement.product_id == Product.id
        ).order_by(SellerAdvertisement.created_at.desc()).all()
        
        if not ads:
            print("❌ No advertisements found")
            return
        
        for i, (ad, seller, product) in enumerate(ads, 1):
            now = datetime.utcnow()
            is_in_time_range = ad.starts_at <= now <= ad.expires_at
            should_be_visible = ad.is_approved and ad.is_active and is_in_time_range
            
            status = "🟢 VISIBLE" if should_be_visible else "🔴 HIDDEN"
            
            print(f"\n{i}. {ad.title}")
            print(f"   Seller: {seller.email}")
            print(f"   Product: {product.name}")
            print(f"   Discount: {ad.discount_percentage}%")
            print(f"   Price: ₱{ad.original_price} → ₱{ad.discounted_price}")
            print(f"   Approved: {'✅' if ad.is_approved else '❌'}")
            print(f"   Active: {'✅' if ad.is_active else '❌'}")
            print(f"   Time Range: {ad.starts_at.strftime('%Y-%m-%d %H:%M')} to {ad.expires_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"   In Time Range: {'✅' if is_in_time_range else '❌'}")
            print(f"   Status: {status}")

def fix_advertisement_issues():
    """Fix common advertisement issues"""
    with app.app_context():
        print("🔧 Fixing Advertisement Issues...")
        
        now = datetime.utcnow()
        fixed_count = 0
        
        # Fix advertisements with future start times
        future_ads = SellerAdvertisement.query.filter(
            SellerAdvertisement.starts_at > now,
            SellerAdvertisement.is_approved == True
        ).all()
        
        for ad in future_ads:
            ad.starts_at = now
            ad.is_active = True
            fixed_count += 1
            print(f"✅ Fixed start time for: {ad.title}")
        
        # Fix inactive approved advertisements
        inactive_ads = SellerAdvertisement.query.filter(
            SellerAdvertisement.is_approved == True,
            SellerAdvertisement.is_active == False,
            SellerAdvertisement.expires_at > now
        ).all()
        
        for ad in inactive_ads:
            ad.is_active = True
            fixed_count += 1
            print(f"✅ Activated: {ad.title}")
        
        if fixed_count > 0:
            db.session.commit()
            print(f"\n💾 Fixed {fixed_count} advertisements")
        else:
            print("✅ No issues found to fix")

def create_test_advertisement():
    """Create a test advertisement for testing"""
    with app.app_context():
        # Get first seller and product
        seller = User.query.filter_by(user_type='seller', is_approved=True).first()
        if not seller:
            print("❌ No approved sellers found")
            return
        
        product = Product.query.filter_by(seller_id=seller.id, status='active').first()
        if not product:
            print("❌ No active products found for seller")
            return
        
        # Create test advertisement
        now = datetime.utcnow()
        expires_at = now + timedelta(days=7)
        
        ad = SellerAdvertisement(
            seller_id=seller.id,
            product_id=product.id,
            title=f'Test Ad - {product.name}',
            description=f'Test advertisement for {product.name}. Get amazing discounts!',
            discount_percentage=15,
            original_price=float(product.price),
            discounted_price=float(product.price) * 0.85,
            promo_message='Test promotion - limited time offer!',
            starts_at=now,
            expires_at=expires_at,
            is_active=True,
            is_approved=True
        )
        
        db.session.add(ad)
        db.session.commit()
        
        print(f"✅ Created test advertisement: {ad.title}")
        print(f"   Product: {product.name}")
        print(f"   Discount: {ad.discount_percentage}%")
        print(f"   Price: ₱{ad.original_price} → ₱{ad.discounted_price}")

def main():
    """Main menu"""
    while True:
        print("\n🛠️  Advertisement Management")
        print("=" * 30)
        print("1. List all advertisements")
        print("2. Fix advertisement issues")
        print("3. Create test advertisement")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == '1':
            list_all_advertisements()
        elif choice == '2':
            fix_advertisement_issues()
        elif choice == '3':
            create_test_advertisement()
        elif choice == '4':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == '__main__':
    main()
