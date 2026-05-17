# Supabase Migration Guide

This document describes the recommended path to migrate this Flask ecommerce app from local MySQL/XAMPP to Supabase PostgreSQL.

## 1) Prepare Supabase

1. Create a Supabase project.
2. Open project settings and copy database credentials.
3. Build your `DATABASE_URL` in SQLAlchemy format:

```
postgresql+psycopg2://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
```

## 2) Configure Environment

1. Copy `.env.example` to `.env`.
2. Fill in `SECRET_KEY` and `DATABASE_URL`.
3. Keep `FLASK_ENV=development` for local testing.

## 3) Install Dependencies

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4) Create Schema in Supabase

Use one of these approaches:

- Quick path:
  - Run `python run.py`
  - The app calls `db.create_all()` and creates tables automatically.
- Controlled migrations (recommended for teams):
  - Use Flask-Migrate and run migration scripts against Supabase.

## 5) Move Existing Data (Optional)

If you have existing MySQL data, migrate to Supabase using one of:

- `pgloader` (recommended for full table migration)
- CSV export/import per table

After importing, verify that IDs and foreign keys are intact.

## 6) Validate the App

Run preflight:

```
python supabase_preflight.py
```

Then run:

```
python run.py
```

Then test:

- User registration/login
- Product creation/editing
- Cart and checkout flow
- Delivery and advertisement features
- Admin approvals and notifications

## 7) Troubleshooting

- If connection fails, confirm:
  - `DATABASE_URL` is correct
  - Supabase password is correct
  - `sslmode=require` is present
- If enum/table creation errors appear:
  - Drop partially created tables/types and rerun migrations
- If old MySQL scripts fail:
  - Update scripts that directly use `pymysql` to SQLAlchemy/Postgres

## Notes

- `config.py` already normalizes `postgres://` to `postgresql://`.
- `config.py` automatically appends `sslmode=require` for Supabase URLs that do not include it.
