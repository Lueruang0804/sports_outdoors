#!/usr/bin/env python3
"""
Database migration script to add EmailVerification table
Run this script to add the email verification functionality to your existing database
"""

import os
import sys
from datetime import datetime, timedelta

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from database import EmailVerification

def migrate_database():
    """Add EmailVerification table to the database"""
    with app.app_context():
        try:
            # Create the EmailVerification table
            db.create_all()
            print("EmailVerification table created successfully!")
            
            # Check if table was created
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'email_verification' in tables:
                print("EmailVerification table verified in database")
            else:
                print("EmailVerification table not found in database")
                
        except Exception as e:
            print(f"Error creating EmailVerification table: {e}")
            return False
    
    return True

if __name__ == "__main__":
    print("Starting EmailVerification table migration...")
    print("=" * 50)
    
    if migrate_database():
        print("=" * 50)
        print("Migration completed successfully!")
        print("Email verification system is now ready to use!")
        print("=" * 50)
    else:
        print("=" * 50)
        print("Migration failed!")
        print("=" * 50)
        sys.exit(1)
