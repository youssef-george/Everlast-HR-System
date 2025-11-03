#!/usr/bin/env python3
"""
Test Dual Database Setup
Tests the dual database configuration and synchronization.
"""

import os
import sys
import logging
import time
from datetime import datetime, date
from flask import Flask

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from extensions import db
from working_sync_service import working_sync_service
from db_helpers import DatabaseManager, BatchOperationContext
from models import User, Department, AttendanceData, LeaveRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DualDatabaseTester:
    """Test the dual database setup and synchronization."""
    
    def __init__(self):
        self.app = None
        self.test_results = {}
    
    def setup_flask_app(self):
        """Set up Flask application for testing."""
        self.app = Flask(__name__)
        self.app.config.from_object(Config)
        
        # Initialize extensions
        db.init_app(self.app)
        working_sync_service.init_app(self.app)
        
        return self.app
    
    def test_database_connections(self):
        """Test both database connections."""
        logger.info("Testing database connections...")
        
        with self.app.app_context():
            try:
                # Test SQLite connection
                from sqlalchemy import text
                db.session.execute(text('SELECT 1'))
                logger.info("✓ SQLite connection successful")
                sqlite_ok = True
            except Exception as e:
                logger.error(f"✗ SQLite connection failed: {str(e)}")
                sqlite_ok = False
            
            # Test PostgreSQL connection
            postgres_ok = working_sync_service.test_postgres_connection()
            if postgres_ok:
                logger.info("✓ PostgreSQL connection successful")
            else:
                logger.error("✗ PostgreSQL connection failed")
            
            self.test_results['connections'] = {
                'sqlite': sqlite_ok,
                'postgres': postgres_ok
            }
            
            return sqlite_ok and postgres_ok
    
    def test_sync_service_status(self):
        """Test sync service status and configuration."""
        logger.info("Testing sync service status...")
        
        with self.app.app_context():
            status = DatabaseManager.get_sync_status()
            
            logger.info(f"Sync enabled: {status['sync_enabled']}")
            logger.info(f"PostgreSQL connected: {status['postgres_connected']}")
            logger.info(f"PostgreSQL engine available: {status['postgres_engine_available']}")
            
            self.test_results['sync_status'] = status
            return status['sync_enabled'] and status['postgres_connected']
    
    def test_create_operations(self):
        """Test create operations with sync."""
        logger.info("Testing create operations...")
        
        with self.app.app_context():
            try:
                # Create a department first
                department = DatabaseManager.create_record(
                    Department,
                    name="IT Department",
                    description="Information Technology"
                )
                
                if not department:
                    logger.error("Failed to create department")
                    return False
                
                logger.info(f"✓ Created department: {department.name}")
                
                # Create a user
                user = DatabaseManager.create_record(
                    User,
                    first_name="John",
                    last_name="Doe",
                    email="john.doe@test.com",
                    password_hash="test_hash",
                    role="employee",
                    department_id=department.id,
                    joining_date=date.today()
                )
                
                if not user:
                    logger.error("Failed to create user")
                    return False
                
                logger.info(f"✓ Created user: {user.get_full_name()}")
                
                # Create attendance record
                attendance = DatabaseManager.create_record(
                    AttendanceData,
                    employee_id=str(user.id),
                    timestamp=datetime.now(),
                    status="check_in",
                    device_id="TEST_DEVICE"
                )
                
                if not attendance:
                    logger.error("Failed to create attendance record")
                    return False
                
                logger.info(f"✓ Created attendance record for user {user.id}")
                
                self.test_results['create_operations'] = {
                    'department_id': department.id,
                    'user_id': user.id,
                    'attendance_id': attendance.id
                }
                
                return True
                
            except Exception as e:
                logger.error(f"Create operations test failed: {str(e)}")
                return False
    
    def test_update_operations(self):
        """Test update operations with sync."""
        logger.info("Testing update operations...")
        
        with self.app.app_context():
            try:
                create_results = self.test_results.get('create_operations', {})
                user_id = create_results.get('user_id')
                
                if not user_id:
                    logger.error("No user ID from create test")
                    return False
                
                # Find and update user
                user = db.session.query(User).filter_by(id=user_id).first()
                if not user:
                    logger.error(f"User {user_id} not found")
                    return False
                
                # Update user
                success = DatabaseManager.update_record(
                    user,
                    phone_number="123-456-7890",
                    position="Software Developer"
                )
                
                if success:
                    logger.info(f"✓ Updated user {user.get_full_name()}")
                    return True
                else:
                    logger.error("Failed to update user")
                    return False
                
            except Exception as e:
                logger.error(f"Update operations test failed: {str(e)}")
                return False
    
    def test_batch_operations(self):
        """Test batch operations without sync."""
        logger.info("Testing batch operations...")
        
        with self.app.app_context():
            try:
                # Create multiple users in batch
                users_data = [
                    {
                        "first_name": "Alice",
                        "last_name": "Smith",
                        "email": "alice@test.com",
                        "password_hash": "hash1",
                        "role": "employee"
                    },
                    {
                        "first_name": "Bob",
                        "last_name": "Johnson",
                        "email": "bob@test.com",
                        "password_hash": "hash2",
                        "role": "manager"
                    },
                    {
                        "first_name": "Carol",
                        "last_name": "Williams",
                        "email": "carol@test.com",
                        "password_hash": "hash3",
                        "role": "employee"
                    }
                ]
                
                with BatchOperationContext():
                    created_users = DatabaseManager.bulk_create_records(User, users_data)
                
                if len(created_users) == len(users_data):
                    logger.info(f"✓ Created {len(created_users)} users in batch")
                    
                    self.test_results['batch_operations'] = {
                        'created_count': len(created_users),
                        'user_ids': [user.id for user in created_users]
                    }
                    return True
                else:
                    logger.error(f"Expected {len(users_data)} users, created {len(created_users)}")
                    return False
                
            except Exception as e:
                logger.error(f"Batch operations test failed: {str(e)}")
                return False
    
    def test_delete_operations(self):
        """Test delete operations with sync."""
        logger.info("Testing delete operations...")
        
        with self.app.app_context():
            try:
                batch_results = self.test_results.get('batch_operations', {})
                user_ids = batch_results.get('user_ids', [])
                
                if not user_ids:
                    logger.error("No user IDs from batch test")
                    return False
                
                # Delete one user
                user_to_delete = db.session.query(User).filter_by(id=user_ids[0]).first()
                if not user_to_delete:
                    logger.error(f"User {user_ids[0]} not found")
                    return False
                
                success = DatabaseManager.delete_record(user_to_delete)
                
                if success:
                    logger.info(f"✓ Deleted user {user_ids[0]}")
                    return True
                else:
                    logger.error("Failed to delete user")
                    return False
                
            except Exception as e:
                logger.error(f"Delete operations test failed: {str(e)}")
                return False
    
    def verify_postgres_sync(self):
        """Verify that data was synced to PostgreSQL."""
        logger.info("Verifying PostgreSQL synchronization...")
        
        with self.app.app_context():
            try:
                # Count records in SQLite
                sqlite_user_count = db.session.query(User).count()
                sqlite_dept_count = db.session.query(Department).count()
                sqlite_attendance_count = db.session.query(AttendanceData).count()
                
                logger.info(f"SQLite counts - Users: {sqlite_user_count}, Departments: {sqlite_dept_count}, Attendance: {sqlite_attendance_count}")
                
                # Count records in PostgreSQL
                with working_sync_service.get_postgres_session() as pg_session:
                    postgres_user_count = pg_session.query(User).count()
                    postgres_dept_count = pg_session.query(Department).count()
                    postgres_attendance_count = pg_session.query(AttendanceData).count()
                
                logger.info(f"PostgreSQL counts - Users: {postgres_user_count}, Departments: {postgres_dept_count}, Attendance: {postgres_attendance_count}")
                
                # Check if counts match (allowing for some delay in sync)
                sync_success = (
                    sqlite_user_count == postgres_user_count and
                    sqlite_dept_count == postgres_dept_count and
                    sqlite_attendance_count == postgres_attendance_count
                )
                
                if sync_success:
                    logger.info("✓ PostgreSQL sync verification successful")
                else:
                    logger.warning("⚠ PostgreSQL sync counts don't match (may need time to sync)")
                
                self.test_results['sync_verification'] = {
                    'sqlite_counts': {
                        'users': sqlite_user_count,
                        'departments': sqlite_dept_count,
                        'attendance': sqlite_attendance_count
                    },
                    'postgres_counts': {
                        'users': postgres_user_count,
                        'departments': postgres_dept_count,
                        'attendance': postgres_attendance_count
                    },
                    'sync_success': sync_success
                }
                
                return sync_success
                
            except Exception as e:
                logger.error(f"PostgreSQL sync verification failed: {str(e)}")
                return False
    
    def run_all_tests(self):
        """Run all tests and return results."""
        logger.info("=" * 60)
        logger.info("STARTING DUAL DATABASE TESTS")
        logger.info("=" * 60)
        
        # Setup
        self.setup_flask_app()
        
        # Run tests
        tests = [
            ("Database Connections", self.test_database_connections),
            ("Sync Service Status", self.test_sync_service_status),
            ("Create Operations", self.test_create_operations),
            ("Update Operations", self.test_update_operations),
            ("Batch Operations", self.test_batch_operations),
            ("Delete Operations", self.test_delete_operations),
            ("PostgreSQL Sync Verification", self.verify_postgres_sync)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            logger.info(f"\n--- Running {test_name} ---")
            try:
                result = test_func()
                results[test_name] = result
                status = "✓ PASSED" if result else "✗ FAILED"
                logger.info(f"{test_name}: {status}")
            except Exception as e:
                results[test_name] = False
                logger.error(f"{test_name}: ✗ FAILED - {str(e)}")
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✓ PASSED" if result else "✗ FAILED"
            logger.info(f"{test_name}: {status}")
        
        logger.info(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed! Dual database setup is working correctly.")
        else:
            logger.warning(f"⚠ {total - passed} test(s) failed. Please check the configuration.")
        
        return results


def main():
    """Main test function."""
    tester = DualDatabaseTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
