#!/usr/bin/env python3
"""
Script to deactivate User13 (or any user by name pattern)
Usage: 
    python deactivate_user13.py                    # Deactivate User13
    python deactivate_user13.py User13             # Deactivate User13
    python deactivate_user13.py "John Doe"         # Deactivate by full name
"""

import sys
from app import create_app
from models import User, db
from datetime import datetime

app = create_app()

with app.app_context():
    # Get search term from command line or use default "User13"
    search_term = sys.argv[1] if len(sys.argv) > 1 else "User13"
    
    print(f"Searching for user: {search_term}")
    
    # Find user by first_name, last_name, email, employee_code, or fingerprint_number
    user = User.query.filter(
        (User.first_name.ilike(f'%{search_term}%')) |
        (User.last_name.ilike(f'%{search_term}%')) |
        (User.email.ilike(f'%{search_term}%')) |
        (User.employee_code.ilike(f'%{search_term}%')) |
        (User.fingerprint_number.ilike(f'%{search_term}%'))
    ).first()
    
    if user:
        print(f"\nFound user:")
        print(f"  ID: {user.id}")
        print(f"  Name: {user.get_full_name()}")
        print(f"  Email: {user.email}")
        print(f"  Employee Code: {user.employee_code or 'N/A'}")
        print(f"  Fingerprint: {user.fingerprint_number or 'N/A'}")
        print(f"  Status: {user.status}")
        print(f"  Role: {user.role}")
        
        if user.status == 'active':
            confirm = input(f"\n⚠️  Are you sure you want to deactivate {user.get_full_name()}? (yes/no): ")
            if confirm.lower() in ['yes', 'y']:
                user.status = 'inactive'
                user.updated_at = datetime.utcnow()
                db.session.commit()
                print(f"✅ User {user.get_full_name()} has been deactivated successfully.")
            else:
                print("❌ Deactivation cancelled.")
        else:
            print(f"⚠️  User {user.get_full_name()} is already {user.status}.")
    else:
        print(f"❌ User '{search_term}' not found. Searching for similar users...")
        all_users = User.query.filter(
            (User.first_name.ilike(f'%{search_term[:5]}%')) |
            (User.last_name.ilike(f'%{search_term[:5]}%'))
        ).limit(10).all()
        
        if all_users:
            print("\nFound similar users:")
            for u in all_users:
                print(f"  - ID: {u.id}, Name: {u.get_full_name()}, Email: {u.email}, Status: {u.status}")
            print("\nTo deactivate a specific user, run:")
            print(f"  python deactivate_user13.py <user_id>")
        else:
            print("No similar users found.")

