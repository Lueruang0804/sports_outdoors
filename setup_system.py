#!/usr/bin/env python3
"""
Complete setup script for Sports and Outdoors Ecommerce System
This script will set up the entire system including database, dependencies, and sample data
"""

import os
import sys
import subprocess
import platform
from dotenv import load_dotenv

load_dotenv()

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
    return True

def setup_virtual_environment():
    """Set up virtual environment"""
    if not os.path.exists("venv"):
        return run_command("python -m venv venv", "Creating virtual environment")
    else:
        print("✅ Virtual environment already exists")
        return True

def activate_virtual_environment():
    """Get the activation command for virtual environment"""
    if platform.system() == "Windows":
        return "venv\\Scripts\\activate"
    else:
        return "source venv/bin/activate"

def install_dependencies():
    """Install Python dependencies"""
    if platform.system() == "Windows":
        pip_command = "venv\\Scripts\\pip"
    else:
        pip_command = "venv/bin/pip"
    
    return run_command(f"{pip_command} install -r requirements.txt", "Installing dependencies")

def setup_database():
    """Set up the database"""
    print("🔄 Setting up database...")
    database_url = os.environ.get("DATABASE_URL", "")
    is_supabase = "supabase.co" in database_url

    if is_supabase:
        try:
            # Ensure tables are created before seeding when using Supabase/Postgres.
            from app import app, db
            with app.app_context():
                db.create_all()
            print("✅ Supabase schema initialized")
        except Exception as e:
            print(f"❌ Supabase schema initialization failed: {str(e)}")
            return False

    try:
        # Import and run the seed data script
        from seed_data import create_sample_data
        create_sample_data()
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {str(e)}")
        return False

def create_startup_scripts():
    """Create startup scripts for different platforms"""
    print("🔄 Creating startup scripts...")
    
    # Windows batch file
    windows_script = """@echo off
echo Starting Sports and Outdoors Ecommerce System...
call venv\\Scripts\\activate
python run.py
pause
"""
    
    with open("start.bat", "w") as f:
        f.write(windows_script)
    
    # Linux/Mac shell script
    unix_script = """#!/bin/bash
echo "Starting Sports and Outdoors Ecommerce System..."
source venv/bin/activate
python run.py
"""
    
    with open("start.sh", "w") as f:
        f.write(unix_script)
    
    # Make shell script executable
    if platform.system() != "Windows":
        os.chmod("start.sh", 0o755)
    
    print("✅ Startup scripts created")
    return True

def main():
    """Main setup function"""
    print("="*60)
    print("🏃‍♂️ SPORTS AND OUTDOORS ECOMMERCE SYSTEM SETUP")
    print("="*60)
    print()
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Set up virtual environment
    if not setup_virtual_environment():
        print("❌ Failed to create virtual environment")
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    # Set up database
    if not setup_database():
        print("❌ Failed to set up database")
        sys.exit(1)
    
    # Create startup scripts
    if not create_startup_scripts():
        print("❌ Failed to create startup scripts")
        sys.exit(1)
    
    print()
    print("="*60)
    print("🎉 SETUP COMPLETED SUCCESSFULLY!")
    print("="*60)
    print()
    print("📋 NEXT STEPS:")
    database_url = os.environ.get("DATABASE_URL", "")
    is_supabase = "supabase.co" in database_url
    if is_supabase:
        print("1. Verify your Supabase DATABASE_URL is set correctly in .env")
        print("2. Run Supabase checks: python supabase_preflight.py")
        start_step = "3"
        open_step = "4"
    else:
        print("1. Make sure XAMPP is running with MySQL")
        print("2. (Optional) Move to Supabase by setting DATABASE_URL in .env")
        start_step = "3"
        open_step = "4"

    print(f"{start_step}. Start the application:")
    if platform.system() == "Windows":
        print("   - Double-click 'start.bat'")
        print("   - Or run: start.bat")
    else:
        print("   - Run: ./start.sh")
        print("   - Or run: bash start.sh")
    print()
    print(f"{open_step}. Open your browser and go to: http://localhost:5000")
    print()
    print("🔑 TEST ACCOUNTS:")
    print("   Admin: admin@sportsandoutdoors.com / admin123")
    print("   Seller: seller@sportsandoutdoors.com / seller123")
    print("   Buyer: buyer@sportsandoutdoors.com / buyer123")
    print("   Rider: rider@sportsandoutdoors.com / rider123")
    print()
    print("📚 FEATURES AVAILABLE:")
    print("   ✅ User registration and authentication")
    print("   ✅ Product management (CRUD operations)")
    print("   ✅ Shopping cart and order management")
    print("   ✅ Admin dashboard and user management")
    print("   ✅ Seller dashboard and sales reports")
    print("   ✅ Rider dashboard and delivery management")
    print("   ✅ Commission tracking")
    print("   ✅ Advertisement management")
    print("   ✅ Notification system")
    print("   ✅ Responsive UI/UX design")
    print()
    print("🚀 Your Sports and Outdoors Ecommerce System is ready to use!")
    print("="*60)

if __name__ == "__main__":
    main()
