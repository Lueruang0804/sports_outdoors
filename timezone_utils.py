#!/usr/bin/env python3
"""
Timezone utilities for Philippine time (UTC+8)
"""

from datetime import datetime, timezone
import pytz

# Philippine timezone
PH_TZ = pytz.timezone('Asia/Manila')

def get_ph_time():
    """Get current Philippine time"""
    return datetime.now(PH_TZ)

def utc_to_ph(utc_dt):
    """Convert UTC datetime to Philippine time"""
    if utc_dt.tzinfo is None:
        # Assume UTC if no timezone info
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(PH_TZ)

def ph_to_utc(ph_dt):
    """Convert Philippine time to UTC"""
    if ph_dt.tzinfo is None:
        # Assume Philippine time if no timezone info
        ph_dt = PH_TZ.localize(ph_dt)
    return ph_dt.astimezone(timezone.utc)

def parse_ph_datetime(datetime_str, format_str='%Y-%m-%dT%H:%M'):
    """Parse datetime string and return Philippine time"""
    dt = datetime.strptime(datetime_str, format_str)
    return PH_TZ.localize(dt)

def format_ph_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """Format datetime for display in Philippine time"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    ph_dt = dt.astimezone(PH_TZ)
    return ph_dt.strftime(format_str)


def isoformat_utc_z(dt):
    """
    Serialize datetime for JSON / JavaScript Date().
    Naive DB values are treated as UTC; output uses explicit Z so clients parse correctly.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        u = dt.replace(tzinfo=timezone.utc)
    else:
        u = dt.astimezone(timezone.utc)
    return u.isoformat().replace('+00:00', 'Z')

def get_ph_datetime_local_input():
    """Get current Philippine time formatted for datetime-local input"""
    ph_now = get_ph_time()
    return ph_now.strftime('%Y-%m-%dT%H:%M')

def is_advertisement_visible(ad):
    """Check if advertisement should be visible based on Philippine time"""
    ph_now = get_ph_time()
    
    # Convert advertisement times to Philippine time if they're UTC
    if ad.starts_at.tzinfo is None:
        ad_starts = ad.starts_at.replace(tzinfo=timezone.utc).astimezone(PH_TZ)
    else:
        ad_starts = ad.starts_at.astimezone(PH_TZ)
    
    if ad.expires_at.tzinfo is None:
        ad_expires = ad.expires_at.replace(tzinfo=timezone.utc).astimezone(PH_TZ)
    else:
        ad_expires = ad.expires_at.astimezone(PH_TZ)
    
    # Check visibility conditions
    is_started = ad_starts <= ph_now
    is_not_expired = ph_now <= ad_expires
    is_in_time_range = is_started and is_not_expired
    should_be_visible = ad.is_active and ad.is_approved and is_in_time_range
    
    return {
        'visible': should_be_visible,
        'started': is_started,
        'not_expired': is_not_expired,
        'in_time_range': is_in_time_range,
        'ph_now': ph_now,
        'ad_starts': ad_starts,
        'ad_expires': ad_expires
    }

def get_time_until_expiry(ad):
    """Get time until advertisement expires in Philippine time"""
    ph_now = get_ph_time()
    
    if ad.expires_at.tzinfo is None:
        ad_expires = ad.expires_at.replace(tzinfo=timezone.utc).astimezone(PH_TZ)
    else:
        ad_expires = ad.expires_at.astimezone(PH_TZ)
    
    return ad_expires - ph_now


def is_admin_site_advertisement_visible(ad):
    """
    Admin-managed site banners (Advertisement model): must be active and not past
    optional expiry date (expiry calendar day is still valid through end of day PH).
    """
    if not ad or not getattr(ad, 'is_active', True):
        return False
    exp = getattr(ad, 'expires_at', None)
    if not exp:
        return True
    ph_now = get_ph_time()
    if exp.tzinfo is None:
        exp_ph = exp.replace(tzinfo=timezone.utc).astimezone(PH_TZ)
    else:
        exp_ph = exp.astimezone(PH_TZ)
    return ph_now.date() <= exp_ph.date()


def is_admin_site_advertisement_claimable(ad):
    """Visible admin banner with a positive discount percentage."""
    if not is_admin_site_advertisement_visible(ad):
        return False
    try:
        pct = int(getattr(ad, 'discount_percentage', 0) or 0)
    except (TypeError, ValueError):
        return False
    return pct > 0
