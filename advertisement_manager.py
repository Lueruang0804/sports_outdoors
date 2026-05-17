#!/usr/bin/env python3
"""
Advertisement Management and Expiration Handler
"""

from app import app, db
from database import SellerAdvertisement, User, Product
from datetime import datetime, timedelta

def check_advertisement_status():
    """Check and display current advertisement status"""
    with app.app_context():
        print("📊 Advertisement Status Report")
        print("=" * 60)
        
        now = datetime.utcnow()
        print(f"⏰ Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Get all advertisements
        ads = db.session.query(SellerAdvertisement, User, Product).join(
            User, SellerAdvertisement.seller_id == User.id
        ).join(
            Product, SellerAdvertisement.product_id == Product.id
        ).order_by(SellerAdvertisement.created_at.desc()).all()
        
        if not ads:
            print("❌ No advertisements found")
            return
        
        # Categorize advertisements
        active_ads = []
        expired_ads = []
        pending_ads = []
        future_ads = []
        
        for ad, seller, product in ads:
            is_started = ad.starts_at <= now
            is_not_expired = now <= ad.expires_at
            is_in_time_range = is_started and is_not_expired
            
            if not ad.is_approved:
                pending_ads.append((ad, seller, product))
            elif not is_started:
                future_ads.append((ad, seller, product))
            elif not is_not_expired:
                expired_ads.append((ad, seller, product))
            elif ad.is_active and is_in_time_range:
                active_ads.append((ad, seller, product))
        
        # Display active advertisements
        print(f"✅ ACTIVE ADVERTISEMENTS ({len(active_ads)}):")
        for ad, seller, product in active_ads:
            time_left = ad.expires_at - now
            print(f"   • {ad.title}")
            print(f"     Product: {product.name}")
            print(f"     Discount: {ad.discount_percentage}% OFF")
            print(f"     Price: ₱{ad.original_price} → ₱{ad.discounted_price}")
            print(f"     Expires: {ad.expires_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"     Time left: {time_left}")
            print()
        
        # Display expired advertisements
        if expired_ads:
            print(f"❌ EXPIRED ADVERTISEMENTS ({len(expired_ads)}):")
            for ad, seller, product in expired_ads:
                time_ago = now - ad.expires_at
                print(f"   • {ad.title}")
                print(f"     Expired: {ad.expires_at.strftime('%Y-%m-%d %H:%M')}")
                print(f"     Time ago: {time_ago}")
                print()
        
        # Display pending advertisements
        if pending_ads:
            print(f"⏳ PENDING APPROVAL ({len(pending_ads)}):")
            for ad, seller, product in pending_ads:
                print(f"   • {ad.title}")
                print(f"     Seller: {seller.email}")
                print(f"     Created: {ad.created_at.strftime('%Y-%m-%d %H:%M')}")
                print()
        
        # Display future advertisements
        if future_ads:
            print(f"🔮 FUTURE ADVERTISEMENTS ({len(future_ads)}):")
            for ad, seller, product in future_ads:
                time_until = ad.starts_at - now
                print(f"   • {ad.title}")
                print(f"     Starts: {ad.starts_at.strftime('%Y-%m-%d %H:%M')}")
                print(f"     Time until start: {time_until}")
                print()
        
        # Summary
        print("📈 SUMMARY:")
        print(f"   Active: {len(active_ads)}")
        print(f"   Expired: {len(expired_ads)}")
        print(f"   Pending: {len(pending_ads)}")
        print(f"   Future: {len(future_ads)}")
        print(f"   Total: {len(ads)}")

def fix_advertisement_times():
    """Fix advertisement start times to current time"""
    with app.app_context():
        print("🔧 Fixing Advertisement Start Times...")
        
        now = datetime.utcnow()
        fixed_count = 0
        
        # Fix advertisements with future start times
        future_ads = SellerAdvertisement.query.filter(
            SellerAdvertisement.starts_at > now,
            SellerAdvertisement.is_approved == True
        ).all()
        
        for ad in future_ads:
            old_start = ad.starts_at
            ad.starts_at = now
            ad.is_active = True
            fixed_count += 1
            print(f"✅ Fixed: {ad.title}")
            print(f"   Old start: {old_start}")
            print(f"   New start: {ad.starts_at}")
        
        if fixed_count > 0:
            db.session.commit()
            print(f"\n💾 Fixed {fixed_count} advertisements")
        else:
            print("✅ No advertisements needed fixing")

def deactivate_expired_advertisements():
    """Deactivate expired advertisements"""
    with app.app_context():
        print("⏰ Deactivating Expired Advertisements...")
        
        now = datetime.utcnow()
        expired_ads = SellerAdvertisement.query.filter(
            SellerAdvertisement.expires_at <= now,
            SellerAdvertisement.is_active == True
        ).all()
        
        deactivated_count = 0
        for ad in expired_ads:
            ad.is_active = False
            deactivated_count += 1
            print(f"✅ Deactivated: {ad.title}")
            print(f"   Expired: {ad.expires_at}")
        
        if deactivated_count > 0:
            db.session.commit()
            print(f"\n💾 Deactivated {deactivated_count} expired advertisements")
        else:
            print("✅ No expired advertisements to deactivate")

def create_test_advertisement():
    """Create a test advertisement for testing"""
    with app.app_context():
        print("🧪 Creating Test Advertisement...")
        
        # Get first approved seller and product
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
        print(f"   Expires: {ad.expires_at}")

def main():
    """Main menu"""
    while True:
        print("\n🛠️  Advertisement Manager")
        print("=" * 30)
        print("1. Check advertisement status")
        print("2. Fix start times (set to now)")
        print("3. Deactivate expired ads")
        print("4. Create test advertisement")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == '1':
            check_advertisement_status()
        elif choice == '2':
            fix_advertisement_times()
        elif choice == '3':
            deactivate_expired_advertisements()
        elif choice == '4':
            create_test_advertisement()
        elif choice == '5':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == '__main__':
    main()
