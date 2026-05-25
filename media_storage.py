"""
Product image storage: Supabase Storage (production) or local static/uploads (dev fallback).

Set on Render (Dashboard → Environment):
  SUPABASE_SERVICE_ROLE_KEY  — Project Settings → API → service_role
  SUPABASE_URL               — optional; derived from DATABASE_URL if omitted
  SUPABASE_STORAGE_BUCKET    — default: product-images (public bucket)
"""

from __future__ import annotations

import io
import os
import re
import uuid
from typing import Optional

import requests
from werkzeug.utils import secure_filename

from upload_storage import db_relative_path, subdir_abs

_CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}


def _content_type(filename: str) -> str:
    ext = os.path.splitext((filename or '').lower())[1]
    return _CONTENT_TYPES.get(ext, 'image/jpeg')


def supabase_project_url() -> str:
    explicit = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    if explicit:
        return explicit
    db = os.environ.get('DATABASE_URL', '')
    m = re.search(r'@db\.([a-z0-9]+)\.supabase\.co', db, re.I)
    if m:
        return f'https://{m.group(1)}.supabase.co'
    return ''


def supabase_storage_enabled() -> bool:
    return bool(supabase_project_url() and os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip())


def supabase_bucket() -> str:
    return os.environ.get('SUPABASE_STORAGE_BUCKET', 'product-images').strip() or 'product-images'


def _supabase_headers(content_type: str) -> dict:
    return {
        'Authorization': f'Bearer {os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()}',
        'Content-Type': content_type,
        'x-upsert': 'true',
    }


def ensure_supabase_bucket() -> None:
    """Create public bucket if missing (no-op when not using Supabase)."""
    if not supabase_storage_enabled():
        return
    base = supabase_project_url()
    bucket = supabase_bucket()
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    try:
        r = requests.get(
            f'{base}/storage/v1/bucket/{bucket}',
            headers={'Authorization': f'Bearer {key}'},
            timeout=15,
        )
        if r.status_code == 200:
            return
        requests.post(
            f'{base}/storage/v1/bucket',
            headers={
                'Authorization': f'Bearer {key}',
                'Content-Type': 'application/json',
            },
            json={'id': bucket, 'name': bucket, 'public': True},
            timeout=15,
        )
    except Exception as exc:
        print(f'WARNING: Supabase bucket setup: {exc}')


def _supabase_upload(object_path: str, data: bytes, content_type: str) -> Optional[str]:
    base = supabase_project_url()
    bucket = supabase_bucket()
    url = f'{base}/storage/v1/object/{bucket}/{object_path}'
    try:
        r = requests.post(
            url,
            headers=_supabase_headers(content_type),
            data=data,
            timeout=60,
        )
        if r.status_code not in (200, 201):
            print(f'ERROR: Supabase upload {r.status_code}: {r.text[:300]}')
            return None
        return f'{base}/storage/v1/object/public/{bucket}/{object_path}'
    except Exception as exc:
        print(f'ERROR: Supabase upload failed: {exc}')
        return None


def _local_save(filename: str, data: bytes) -> str:
    products_dir = subdir_abs('products')
    path = os.path.join(products_dir, filename)
    with open(path, 'wb') as f:
        f.write(data)
    return db_relative_path('products', filename)


def _unique_filename(original: str) -> str:
    base = secure_filename(original) or 'product.jpg'
    name, ext = os.path.splitext(base)
    if not ext:
        ext = '.jpg'
    import time
    return f'{name}_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}'


def save_product_image_bytes(data: bytes, filename: str = 'product.jpg') -> Optional[str]:
    """Save product image; returns value for Product.image_url (URL or uploads/... path)."""
    if not data:
        return None
    unique = _unique_filename(filename)
    if supabase_storage_enabled():
        ensure_supabase_bucket()
        object_path = f'products/{unique}'
        public_url = _supabase_upload(object_path, data, _content_type(unique))
        if public_url:
            return public_url
        print('WARNING: Supabase upload failed; saving locally.')
    return _local_save(unique, data)


def save_product_image_file(file_storage) -> Optional[str]:
    if not file_storage or not file_storage.filename:
        return None
    try:
        data = file_storage.read()
        return save_product_image_bytes(data, file_storage.filename)
    except Exception as exc:
        print(f'ERROR: product image read: {exc}')
        return None


def resolve_product_image_url(stored_value, external: bool = False) -> str:
    """
    Browser/API src for Product.image_url.
    Supports https:// Supabase URLs, uploads/products/..., and legacy /static/images/...
    """
    if not stored_value or not str(stored_value).strip():
        return ''
    v = str(stored_value).strip().replace('\\', '/')
    if v.startswith(('http://', 'https://')):
        return v
    v = v.lstrip('/')
    if v.startswith('static/'):
        v = v[len('static/') :]
    try:
        from flask import url_for
        path = url_for('static', filename=v, _external=external)
        return path
    except RuntimeError:
        base = (
            os.environ.get('APP_BASE_URL')
            or os.environ.get('RENDER_EXTERNAL_URL')
            or 'http://localhost:5000'
        ).rstrip('/')
        return f'{base}/static/{v}'


def storage_status() -> dict:
    return {
        'mode': 'supabase' if supabase_storage_enabled() else 'local',
        'supabase_configured': supabase_storage_enabled(),
        'supabase_url': supabase_project_url() or None,
        'supabase_bucket': supabase_bucket() if supabase_storage_enabled() else None,
    }
