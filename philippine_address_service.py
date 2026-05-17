"""
Philippine address data (PSGC) — region → province → city/municipality → barangay.
JSON files live in data/philippine_addresses/ (from philippine-addresses dataset).
Values returned to clients are human-readable names for storage in User.address_* fields.
"""
from __future__ import annotations

import json
import os
from typing import List

_BASE = os.path.join(os.path.dirname(__file__), 'data', 'philippine_addresses')
_cache: dict = {}


def _path(*parts: str) -> str:
    return os.path.join(_BASE, *parts)


def _load_json(key: str, filename: str):
    if key not in _cache:
        with open(_path(filename), encoding='utf-8') as f:
            _cache[key] = json.load(f)
    return _cache[key]


def get_regions_list():
    """List of region dicts from region.json, sorted by id."""
    data = _load_json('regions_raw', 'region.json')
    return sorted(data, key=lambda r: int(r.get('id', 0)))


def get_provinces_for_region(region_code: str) -> List[dict]:
    """Deduplicate by province_code; order by name."""
    region_code = (region_code or '').strip()
    if not region_code:
        return []
    provinces = _load_json('provinces_raw', 'province.json')
    seen: dict[str, str] = {}
    for p in provinces:
        if p.get('region_code') == region_code:
            pc = p.get('province_code')
            if pc and pc not in seen:
                seen[pc] = p.get('province_name', '')
    return [
        {'province_code': k, 'province_name': v}
        for k, v in sorted(seen.items(), key=lambda x: (x[1] or '', x[0]))
    ]


def get_cities_for_province(province_code: str) -> List[dict]:
    province_code = (province_code or '').strip()
    if not province_code:
        return []
    cities = _load_json('cities_raw', 'city.json')
    seen: dict[str, str] = {}
    for c in cities:
        if c.get('province_code') == province_code:
            cc = c.get('city_code')
            if cc and cc not in seen:
                seen[cc] = c.get('city_name', '')
    return [
        {'city_code': k, 'city_name': v}
        for k, v in sorted(seen.items(), key=lambda x: (x[1] or '', x[0]))
    ]


def get_barangays_for_city(city_code: str) -> List[dict]:
    city_code = (city_code or '').strip()
    if not city_code:
        return []
    barangays = _load_json('barangays_raw', 'barangay.json')
    seen: dict[str, str] = {}
    for b in barangays:
        if b.get('city_code') == city_code:
            bc = b.get('brgy_code')
            if bc and bc not in seen:
                seen[bc] = b.get('brgy_name', '')
    return [
        {'brgy_code': k, 'brgy_name': v}
        for k, v in sorted(seen.items(), key=lambda x: (x[1] or '', x[0]))
    ]
