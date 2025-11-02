#!/usr/bin/env python3
"""
Script to find user ID by name
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import User

def find_user_by_name(first_name, last_name):
    """Find user by first and last name"""
    
    app = create_app()
    with app.app_context():
        users = User.query.filter(
            User.first_name.ilike(f'%{first_name}%'),
            User.last_name.ilike(f'%{last_name}%')
        ).all()
        
        if users:
            for user in users:
                print(f"Found user: {user.get_full_name()} (ID: {user.id})")
        else:
            print(f"No user found with name containing '{first_name} {last_name}'")
            
        # Also show all active users for reference
        print("\nAll active users:")
        all_users = User.query.filter_by(status='active').all()
        for user in all_users:
            print(f"  {user.get_full_name()} (ID: {user.id})")

if __name__ == "__main__":
    find_user_by_name("Youssef", "George")
