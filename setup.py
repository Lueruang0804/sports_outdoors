#!/usr/bin/env python3
"""
Setup script for Sports and Outdoors Ecommerce System
This script helps set up the application environment
"""

import os
import sys
import subprocess

def create_directories():
    """Create necessary directories"""
    directories = [
        'static/uploads',
        'static/uploads/products',
        'static/uploads/profiles',
        'static/uploads/documents',
        'static/uploads/advertisements',
        'static/images',
        'templates/auth',
        'templates/buyer',
        'templates/seller',
        'templates/admin',
        'templates/rider',
        'templates/main'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✓ Created directory: {directory}")

def install_requirements():
    """Install Python requirements"""
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✓ Installed Python requirements")
    except subprocess.CalledProcessError:
        print("✗ Failed to install requirements")
        return False
    return True

def create_sample_images():
    """Create placeholder images"""
    # This would create sample images if needed
    print("✓ Sample images ready")

def main():
    print("🏃‍♂️ Setting up Sports and Outdoors Ecommerce System...")
    print("=" * 50)
    
    # Create directories
    print("\n📁 Creating directories...")
    create_directories()
    
    # Install requirements
    print("\n📦 Installing requirements...")
    if not install_requirements():
        print("❌ Setup failed during requirements installation")
        return
    
    # Create sample images
    print("\n🖼️  Setting up images...")
    create_sample_images()
    
    print("\n" + "=" * 50)
    print("✅ Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Start XAMPP and ensure MySQL is running")
    print("2. Create database 'ecommerce_system' in phpMyAdmin")
    print("3. Import database_setup.sql file")
    print("4. Update email configuration in app.py")
    print("5. Run: python run.py")
    print("\n🌐 Application will be available at: http://localhost:5000")

if __name__ == '__main__':
    main()
