#!/usr/bin/env python3
"""Create public product-images bucket and optionally sync key to Render."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def main():
    from sqlalchemy import create_engine, text
    from config import _build_database_url
    from media_storage import (
        ensure_supabase_bucket,
        save_product_image_bytes,
        storage_status,
        supabase_project_url,
        supabase_storage_enabled,
    )

    db_url = _build_database_url(os.environ.get('DATABASE_URL', ''))
    if not db_url:
        print('ERROR: DATABASE_URL not set in .env')
        return 1

    print('Supabase URL:', supabase_project_url() or '(could not derive — set SUPABASE_URL)')

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
                VALUES ('product-images', 'product-images', true, 52428800, NULL)
                ON CONFLICT (id) DO UPDATE SET public = true, name = EXCLUDED.name
            """))
            conn.commit()
            rows = conn.execute(text(
                "SELECT id, public FROM storage.buckets WHERE id = 'product-images'"
            )).fetchall()
            print('Bucket row:', rows)
    except Exception as exc:
        print('SQL bucket setup:', exc)

    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    if not key:
        print()
        print('SUPABASE_SERVICE_ROLE_KEY missing in .env')
        print('Supabase Dashboard → Project Settings → API → service_role → copy key')
        print('Add to .env: SUPABASE_SERVICE_ROLE_KEY=eyJ...')
        print('Then re-run: python scripts/setup_supabase_storage.py')
        return 1

    ensure_supabase_bucket()
    test = save_product_image_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100, 'setup_test.jpg')
    print('Storage status:', storage_status())
    print('Test upload:', 'OK' if test and test.startswith('http') else 'FAILED', test or '')
    return 0 if supabase_storage_enabled() and test else 1


if __name__ == '__main__':
    sys.exit(main())
