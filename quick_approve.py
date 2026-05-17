#!/usr/bin/env python3
"""
Quick Approve All Users
"""

from app import app, db
from database import User

def approve_all():
    with app.app_context():
        # Approve all users
        users = User.query.filter_by(is_approved=False).all()
        print(f'👥 Found {len(users)} unapproved users')
        
        for user in users:
            user.is_approved = True
            print(f'✅ Approved: {user.email}')
        
        db.session.commit()
        print(f'🎉 All {len(users)} users are now approved and can login!')
        
        # Show final status
        all_users = User.query.all()
        print(f'\n📊 Final Status:')
        for user in all_users:
            print(f'{user.email} - Approved: {user.is_approved}')

if __name__ == '__main__':
    approve_all()
