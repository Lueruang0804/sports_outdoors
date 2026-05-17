#!/usr/bin/env python3
"""
Sports and Outdoors Ecommerce System
Run script for the Flask application
"""

import os
from app import app, db

if __name__ == '__main__':
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")
    
    # Run the application
    print("Starting Sports and Outdoors Ecommerce System...")
    print("Application will be available at: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
