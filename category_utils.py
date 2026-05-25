"""Canonical product categories and alias matching (& vs and, URL slugs)."""

import re

SHOP_CATEGORIES = [
    'Fitness Equipment',
    'Camping & Hiking Gear',
    'Sports Apparel',
    'Cycling & Bikes',
    'Water Sports',
    'Team Sports Equipment',
]

# URL-safe slugs for links (avoids breaking query strings on "&")
CATEGORY_SLUGS = {
    'fitness-equipment': 'Fitness Equipment',
    'camping-hiking-gear': 'Camping & Hiking Gear',
    'sports-apparel': 'Sports Apparel',
    'cycling-bikes': 'Cycling & Bikes',
    'water-sports': 'Water Sports',
    'team-sports-equipment': 'Team Sports Equipment',
}

_SLUG_BY_CANONICAL = {v: k for k, v in CATEGORY_SLUGS.items()}

# Legacy / registration strings -> canonical display name
_LEGACY_TO_CANONICAL = {
    'camping and hiking gear': 'Camping & Hiking Gear',
    'camping & hiking gear': 'Camping & Hiking Gear',
    'cycling and bikes': 'Cycling & Bikes',
    'cycling & bikes': 'Cycling & Bikes',
}

# All DB values that belong to each canonical category (for IN filters)
_CATEGORY_DB_VARIANTS = {
    'Camping & Hiking Gear': ['Camping & Hiking Gear', 'Camping and Hiking Gear'],
    'Cycling & Bikes': ['Cycling & Bikes', 'Cycling and Bikes'],
}


def _normalize_key(value):
    """Lowercase key: treat 'and' like '&' for matching."""
    s = re.sub(r'\s+', ' ', (value or '').strip().lower())
    s = re.sub(r'\s+and\s+', ' & ', s)
    return s


def normalize_category(value):
    """Map any category string to the canonical shop name (or strip original)."""
    raw = (value or '').strip()
    if not raw:
        return raw
    slug_key = raw.lower().replace('_', '-')
    if slug_key in CATEGORY_SLUGS:
        return CATEGORY_SLUGS[slug_key]
    key = _normalize_key(raw)
    if key in _LEGACY_TO_CANONICAL:
        return _LEGACY_TO_CANONICAL[key]
    for canonical in SHOP_CATEGORIES:
        if _normalize_key(canonical) == key:
            return canonical
    return raw


def category_slug(canonical_name):
    """Slug for url_for(category=...) — safe in HTML hidden fields and URLs."""
    canonical = normalize_category(canonical_name)
    return _SLUG_BY_CANONICAL.get(canonical, '')


def category_match_values(value):
    """All product.category values to include when filtering by category param."""
    raw = (value or '').strip()
    if not raw:
        return []
    slug_key = raw.lower().replace('_', '-')
    if slug_key in CATEGORY_SLUGS:
        canonical = CATEGORY_SLUGS[slug_key]
    else:
        canonical = normalize_category(raw)
    variants = _CATEGORY_DB_VARIANTS.get(canonical)
    if variants:
        return variants
    return [canonical] if canonical else []


def categories_for_template():
    """Sidebar / home: list of {name, slug} for links."""
    return [
        {'name': name, 'slug': category_slug(name)}
        for name in SHOP_CATEGORIES
    ]
