"""
Product images: Supabase Storage (if configured) else PostgreSQL (Render) else local files (dev).

Supabase (optional): SUPABASE_SERVICE_ROLE_KEY + SUPABASE_URL
Database fallback: uses existing DATABASE_URL — no extra setup, survives deploy
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

DB_MEDIA_PREFIX = 'product-media://'

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


def is_db_media_marker(value) -> bool:
    return str(value or '').strip().startswith(DB_MEDIA_PREFIX)


def db_media_marker(product_id: int) -> str:
    return f'{DB_MEDIA_PREFIX}{int(product_id)}'


def supabase_project_url() -> str:
    explicit = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    if explicit:
        return explicit
    db = os.environ.get('DATABASE_URL', '')
    m = re.search(r'@db\.([a-z0-9]+)\.supabase\.co', db, re.I)
    if m:
        return f'https://{m.group(1)}.supabase.co'
    m = re.search(r'postgres\.([a-z0-9]+)(?:[:@])', db, re.I)
    if m:
        return f'https://{m.group(1)}.supabase.co'
    return ''


def supabase_storage_enabled() -> bool:
    return bool(supabase_project_url() and os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip())


def use_database_image_storage() -> bool:
    """Store bytes in Postgres — default on Render when Supabase Storage is not set up."""
    if supabase_storage_enabled():
        return False
    if os.environ.get('PRODUCT_IMAGES_IN_DB', '').lower() in ('1', 'true', 'yes'):
        return True
    if os.environ.get('RENDER', '').strip():
        return True
    return False


def supabase_bucket() -> str:
    return os.environ.get('SUPABASE_STORAGE_BUCKET', 'product-images').strip() or 'product-images'


def _supabase_headers(content_type: str) -> dict:
    return {
        'Authorization': f'Bearer {os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()}',
        'Content-Type': content_type,
        'x-upsert': 'true',
    }


def ensure_supabase_bucket() -> None:
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


def placeholder_image_bytes(name: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (300, 200), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', 16)
    except Exception:
        font = ImageFont.load_default()
    text = name[:25] + '...' if len(name) > 25 else name
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * 10
    draw.text(((300 - tw) // 2, 90), text, fill=(100, 100, 100), font=font)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return buf.getvalue()


def save_product_image_bytes(data: bytes, filename: str = 'product.jpg') -> Optional[str]:
    if not data:
        return None
    unique = _unique_filename(filename)
    if supabase_storage_enabled():
        ensure_supabase_bucket()
        public_url = _supabase_upload(f'products/{unique}', data, _content_type(unique))
        if public_url:
            return public_url
        print('WARNING: Supabase upload failed; using database/local fallback.')
    if use_database_image_storage():
        return None
    return _local_save(unique, data)


def save_product_image_file(file_storage) -> Optional[str]:
    if not file_storage or not file_storage.filename:
        return None
    try:
        return save_product_image_bytes(file_storage.read(), file_storage.filename)
    except Exception as exc:
        print(f'ERROR: product image read: {exc}')
        return None


def apply_product_image(product, file_storage=None, image_bytes: Optional[bytes] = None, filename: str = 'product.jpg'):
    """
    Attach image to a Product row (must be flushed so product.id exists for DB storage).
    Caller commits the session.
    """
    from database import db

    data = image_bytes
    fname = filename or 'product.jpg'
    if file_storage and getattr(file_storage, 'filename', None):
        if file_storage.filename:
            fname = file_storage.filename
            data = file_storage.read()
    if not data:
        data = placeholder_image_bytes(product.name or 'Product')
        fname = 'placeholder.jpg'

    if supabase_storage_enabled():
        url = save_product_image_bytes(data, fname)
        if url:
            product.image_url = url
            product.image_data = None
            product.image_mimetype = None
            return
        print('WARNING: Supabase failed; falling back to database storage.')

    if use_database_image_storage():
        product.image_data = data
        product.image_mimetype = _content_type(fname)
        if not product.id:
            db.session.flush()
        product.image_url = db_media_marker(product.id)
        return

    product.image_data = None
    product.image_mimetype = None
    product.image_url = save_product_image_bytes(data, fname) or db_relative_path('products', _unique_filename(fname))


def external_product_image_url(stored_value) -> str:
    """Full https URL for mobile/API clients (product-media://, uploads/, etc.)."""
    if not stored_value or not str(stored_value).strip():
        return ''
    return resolve_product_image_url(stored_value, external=True) or ''


def resolve_product_image_url(stored_value, external: bool = False) -> str:
    if not stored_value or not str(stored_value).strip():
        return ''
    v = str(stored_value).strip().replace('\\', '/')
    if v.startswith(('http://', 'https://')):
        return v
    if is_db_media_marker(v):
        pid = v.split('://', 1)[1]
        try:
            from flask import url_for
            return url_for('main.product_media', product_id=int(pid), _external=external)
        except RuntimeError:
            base = (
                os.environ.get('APP_BASE_URL')
                or os.environ.get('RENDER_EXTERNAL_URL')
                or 'http://localhost:5000'
            ).rstrip('/')
            return f'{base}/product-media/{pid}'
    v = v.lstrip('/')
    if v.startswith('static/'):
        v = v[len('static/') :]
    try:
        from flask import url_for
        return url_for('static', filename=v, _external=external)
    except RuntimeError:
        base = (
            os.environ.get('APP_BASE_URL')
            or os.environ.get('RENDER_EXTERNAL_URL')
            or 'http://localhost:5000'
        ).rstrip('/')
        return f'{base}/static/{v}'


def storage_status() -> dict:
    if supabase_storage_enabled():
        mode = 'supabase'
    elif use_database_image_storage():
        mode = 'database'
    else:
        mode = 'local'
    return {
        'mode': mode,
        'supabase_configured': supabase_storage_enabled(),
        'supabase_url': supabase_project_url() or None,
        'supabase_bucket': supabase_bucket() if supabase_storage_enabled() else None,
        'database_image_storage': use_database_image_storage(),
    }
