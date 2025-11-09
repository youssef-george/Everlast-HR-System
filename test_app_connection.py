#!/usr/bin/env python3
"""
Test Flask app database connection
"""
import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import User

def test_app_connection():
    """Test if Flask app can connect to database and read data"""
    app = create_app()
    
    with app.app_context():
        try:
            # Test database connection
            print('🔍 Testing Flask app database connection...')
            
            # Count users
            user_count = User.query.count()
            print(f'👥 Users found via Flask app: {user_count}')
            
            # Get admin users
            admin_users = User.query.filter_by(role='admin').all()
            print(f'👑 Admin users:')
            for admin in admin_users:
                print(f'  - {admin.first_name} {admin.last_name} ({admin.email})')
            
            # Test login credentials
            test_admin = User.query.filter_by(email='admin@everlast.com').first()
            if test_admin:
                print(f'✅ Test admin user found: {test_admin.email}')
            else:
                print('❌ Test admin user NOT found')
                
            # Check existing admin
            existing_admin = User.query.filter_by(email='erp@everlastwellness.com').first()
            if existing_admin:
                print(f'✅ Existing admin found: {existing_admin.email}')
            else:
                print('❌ Existing admin NOT found')
            
        except Exception as e:
            print(f'❌ Flask app database error: {e}')

if __name__ == '__main__':
    test_app_connection()











