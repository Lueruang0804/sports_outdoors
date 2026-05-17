#!/usr/bin/env python3
"""
Background Tasks for Advertisement System
"""

from app import app, db
from database import SellerAdvertisement
from datetime import datetime
from timezone_utils import get_ph_time

def deactivate_expired_advertisements():
    """Deactivate advertisements that have expired"""
    with app.app_context():
        now = get_ph_time()
        expired_ads = SellerAdvertisement.query.filter(
            SellerAdvertisement.is_active == True,
            SellerAdvertisement.expires_at <= now
        ).all()
        
        count = 0
        for ad in expired_ads:
            ad.is_active = False
            count += 1
            print(f"✅ Deactivated expired ad: {ad.title} (expired: {ad.expires_at})")
        
        if count > 0:
            db.session.commit()
            print(f"💾 Deactivated {count} expired advertisements")
        else:
            print("✅ No expired advertisements found")

def check_advertisement_status():
    """Check current advertisement status"""
    with app.app_context():
        now = get_ph_time()
        
        # Count active advertisements
        active_count = SellerAdvertisement.query.filter(
            SellerAdvertisement.is_active == True,
            SellerAdvertisement.is_approved == True,
            SellerAdvertisement.starts_at <= now,
            SellerAdvertisement.expires_at > now
        ).count()
        
        # Count expired advertisements
        expired_count = SellerAdvertisement.query.filter(
            SellerAdvertisement.expires_at <= now,
            SellerAdvertisement.is_active == True
        ).count()
        
        print(f"📊 Advertisement Status:")
        print(f"   Active: {active_count}")
        print(f"   Expired (need deactivation): {expired_count}")
        
        return expired_count > 0

if __name__ == '__main__':
    deactivate_expired_advertisements()
