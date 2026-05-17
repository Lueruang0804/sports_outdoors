#!/usr/bin/env python3
"""
Migration script to add rider-specific fields to the User table
Run this script to add the new columns to your existing database
"""

import pymysql
import os

def migrate_database():
    """Add rider-specific fields to the User table"""
    
    try:
        # Connect to MySQL database
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='',
            database='ecommerce_system',
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("SHOW COLUMNS FROM user")
        columns = [column[0] for column in cursor.fetchall()]
        
        # Add rider-specific columns if they don't exist
        if 'drivers_license' not in columns:
            cursor.execute("ALTER TABLE user ADD COLUMN drivers_license VARCHAR(255)")
            print("Added drivers_license column")
        else:
            print("drivers_license column already exists")
            
        if 'vehicle_type' not in columns:
            cursor.execute("ALTER TABLE user ADD COLUMN vehicle_type VARCHAR(50)")
            print("Added vehicle_type column")
        else:
            print("vehicle_type column already exists")
            
        if 'vehicle_plate' not in columns:
            cursor.execute("ALTER TABLE user ADD COLUMN vehicle_plate VARCHAR(20)")
            print("Added vehicle_plate column")
        else:
            print("vehicle_plate column already exists")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting database migration for rider fields...")
    success = migrate_database()
    
    if success:
        print("\nMigration completed successfully!")
        print("You can now register riders with driver's license upload.")
    else:
        print("\nMigration failed. Please check the error messages above.")
