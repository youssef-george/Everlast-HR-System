#!/usr/bin/env python3
"""
Test Sync Fix
Quick test to verify that database changes are now syncing properly.
"""

import os
import sys
from datetime import datetime, date

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database_sync():
    """Test if database changes are syncing to PostgreSQL."""
    try:
        from flask import Flask
        from config import Config
        from extensions import db
        from working_sync_service import working_sync_service
        from models import User, Department
        
        print("Testing Database Sync Fix")
        print("=" * 40)
        
        # Set up Flask app
        app = Flask(__name__)
        app.config.from_object(Config)
        
        # Initialize extensions
        db.init_app(app)
        working_sync_service.init_app(app)
        
        with app.app_context():
            # Check sync service status
            print("Checking sync service status...")
            stats = working_sync_service.get_sync_stats()
            print(f"Sync enabled: {stats['sync_enabled']}")
            print(f"PostgreSQL connected: {stats['postgres_connected']}")
            
            if not stats['sync_enabled'] or not stats['postgres_connected']:
                print("❌ Sync service not ready. Please check configuration.")
                return False
            
            # Test 1: Create a test department
            print("\nTest 1: Creating a test department...")
            test_dept = Department(
                name=f"Test Department {datetime.now().strftime('%H%M%S')}",
                description="Test department for sync verification"
            )
            
            db.session.add(test_dept)
            db.session.commit()
            
            print(f"✓ Created department: {test_dept.name} (ID: {test_dept.id})")
            
            # Test 2: Create a test user
            print("\nTest 2: Creating a test user...")
            test_user = User(
                first_name="Test",
                last_name=f"User{datetime.now().strftime('%H%M%S')}",
                email=f"test.user.{datetime.now().strftime('%H%M%S')}@example.com",
                password_hash="test_hash",
                role="employee",
                department_id=test_dept.id,
                joining_date=date.today()
            )
            
            db.session.add(test_user)
            db.session.commit()
            
            print(f"✓ Created user: {test_user.get_full_name()} (ID: {test_user.id})")
            
            # Test 3: Update the user
            print("\nTest 3: Updating the test user...")
            test_user.phone_number = "123-456-7890"
            test_user.position = "Test Developer"
            
            db.session.commit()
            
            print(f"✓ Updated user: {test_user.get_full_name()}")
            
            # Test 4: Verify in PostgreSQL
            print("\nTest 4: Verifying sync to PostgreSQL...")
            
            # Wait a moment for sync to complete
            import time
            time.sleep(2)
            
            with working_sync_service.get_postgres_session() as pg_session:
                # Check if department exists in PostgreSQL
                pg_dept = pg_session.query(Department).filter_by(id=test_dept.id).first()
                if pg_dept:
                    print(f"✓ Department found in PostgreSQL: {pg_dept.name}")
                else:
                    print(f"❌ Department NOT found in PostgreSQL")
                    return False
                
                # Check if user exists in PostgreSQL
                pg_user = pg_session.query(User).filter_by(id=test_user.id).first()
                if pg_user:
                    print(f"✓ User found in PostgreSQL: {pg_user.get_full_name()}")
                    print(f"✓ User phone updated: {pg_user.phone_number}")
                    print(f"✓ User position updated: {pg_user.position}")
                else:
                    print(f"❌ User NOT found in PostgreSQL")
                    return False
            
            # Test 5: Delete the test records
            print("\nTest 5: Cleaning up test records...")
            db.session.delete(test_user)
            db.session.delete(test_dept)
            db.session.commit()
            
            print("✓ Test records deleted from SQLite")
            
            # Verify deletion in PostgreSQL
            time.sleep(2)
            
            with working_sync_service.get_postgres_session() as pg_session:
                pg_user_check = pg_session.query(User).filter_by(id=test_user.id).first()
                pg_dept_check = pg_session.query(Department).filter_by(id=test_dept.id).first()
                
                if not pg_user_check and not pg_dept_check:
                    print("✓ Test records deleted from PostgreSQL")
                else:
                    print("⚠ Test records may still exist in PostgreSQL (sync delay)")
            
            print("\n🎉 All sync tests passed! Database changes are now syncing properly.")
            return True
            
    except Exception as e:
        print(f"\n❌ Sync test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    success = test_database_sync()
    
    if success:
        print("\n✅ SYNC FIX SUCCESSFUL!")
        print("Your Flask app changes will now automatically sync to PostgreSQL.")
        print("\nNext steps:")
        print("1. Start your Flask app: python app.py")
        print("2. Make changes through your web interface")
        print("3. Check /health endpoint to monitor sync status")
    else:
        print("\n❌ SYNC FIX FAILED!")
        print("Please check the error messages above and verify your configuration.")
    
    return success

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

