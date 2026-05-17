#!/usr/bin/env python3
"""
Supabase preflight checks for Sports and Outdoors Ecommerce System.

This script validates:
1) Environment variables
2) Database connection
3) Table creation/readability via SQLAlchemy models
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()


def fail(message):
    print(f"ERROR: {message}")
    return False


def ok(message):
    print(f"SUCCESS: {message}")
    return True


def validate_database_url():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return fail("DATABASE_URL is not set. Copy .env.example to .env and fill DATABASE_URL.")

    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://", "postgres://")):
        return fail("DATABASE_URL does not look like a PostgreSQL URL.")

    if "supabase.co" not in database_url:
        print("WARNING: DATABASE_URL does not contain supabase.co. Continuing anyway.")

    if "sslmode=" not in database_url:
        print("WARNING: DATABASE_URL missing sslmode=require. config.py will auto-append for supabase URLs.")

    return ok("DATABASE_URL format looks valid")


def check_db_connection():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return fail("Skipping DB connection check because DATABASE_URL is not set.")

    try:
        from app import app, db
    except Exception as exc:
        return fail(f"Application import failed before DB check: {exc}")

    try:
        with app.app_context():
            # Connectivity probe
            db.session.execute(text("SELECT 1"))
            ok("Database connection successful")

            # Ensure schema exists
            db.create_all()
            ok("Schema create/check passed")

            # Smoke query from core model
            from database import User
            _ = User.query.count()
            ok("Core table query passed (user table)")
        return True
    except Exception as exc:
        return fail(f"Database check failed: {exc}")


def main():
    print("=" * 60)
    print("SUPABASE PREFLIGHT CHECK")
    print("=" * 60)

    checks = [
        ("Validate DATABASE_URL", validate_database_url),
        ("Connection and schema check", check_db_connection),
    ]

    passed = 0
    for name, fn in checks:
        print(f"\n{name}")
        print("-" * 40)
        if fn():
            passed += 1

    print("\n" + "=" * 60)
    print(f"Checks passed: {passed}/{len(checks)}")
    if passed == len(checks):
        print("ALL CHECKS PASSED. Ready for Supabase run.")
        print("Next:")
        print("1. python run.py")
        print("2. python test_system.py")
        return 0

    print("Some checks failed. Fix the error above, then rerun:")
    print("python supabase_preflight.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
