#!/usr/bin/env python3
"""
Example Usage of Dual Database Setup
Demonstrates how to use the dual database system in your Flask application.
"""

import os
import sys
from datetime import datetime, date
from flask import Flask

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from extensions import db
from sync_service import sync_service
from db_helpers import (
    DatabaseManager, 
    BatchOperationContext,
    create_user, 
    update_user, 
    create_attendance_record,
    create_leave_request
)
from models import User, Department, AttendanceData, LeaveRequest


def setup_app():
    """Set up Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    sync_service.init_app(app)
    
    return app


def example_basic_operations():
    """Example of basic CRUD operations with automatic sync."""
    print("\n=== Basic Operations Example ===")
    
    # Create a department
    department = DatabaseManager.create_record(
        Department,
        name="Engineering",
        description="Software Engineering Department"
    )
    print(f"Created department: {department.name}")
    
    # Create a user with automatic sync to PostgreSQL
    user = create_user(
        first_name="Alice",
        last_name="Johnson",
        email="alice.johnson@company.com",
        password_hash="secure_hash_here",
        role="employee",
        department_id=department.id,
        joining_date=date.today(),
        phone_number="555-0123"
    )
    
    if user:
        print(f"Created user: {user.get_full_name()} (ID: {user.id})")
        
        # Update user information
        success = update_user(
            user,
            position="Senior Developer",
            salary=75000.0,
            currency="USD"
        )
        
        if success:
            print(f"Updated user: {user.get_full_name()}")
        
        # Create attendance record
        attendance = create_attendance_record(
            employee_id=str(user.id),
            timestamp=datetime.now(),
            status="check_in",
            device_id="MAIN_ENTRANCE"
        )
        
        if attendance:
            print(f"Created attendance record for {user.get_full_name()}")
        
        # Create leave request
        leave_request = create_leave_request(
            user_id=user.id,
            leave_type="annual",
            start_date=date(2024, 12, 20),
            end_date=date(2024, 12, 24),
            reason="Christmas vacation",
            status="pending"
        )
        
        if leave_request:
            print(f"Created leave request for {user.get_full_name()}")
    
    return user, department


def example_batch_operations():
    """Example of batch operations without individual sync."""
    print("\n=== Batch Operations Example ===")
    
    # Create multiple users efficiently
    users_data = [
        {
            "first_name": "Bob",
            "last_name": "Smith",
            "email": "bob.smith@company.com",
            "password_hash": "hash1",
            "role": "manager",
            "joining_date": date(2023, 1, 15)
        },
        {
            "first_name": "Carol",
            "last_name": "Davis",
            "email": "carol.davis@company.com",
            "password_hash": "hash2",
            "role": "employee",
            "joining_date": date(2023, 3, 10)
        },
        {
            "first_name": "David",
            "last_name": "Wilson",
            "email": "david.wilson@company.com",
            "password_hash": "hash3",
            "role": "employee",
            "joining_date": date(2023, 6, 1)
        }
    ]
    
    # Use batch context to avoid individual syncs
    with BatchOperationContext():
        created_users = DatabaseManager.bulk_create_records(User, users_data)
        print(f"Created {len(created_users)} users in batch operation")
        
        # Create attendance records for all users
        attendance_data = []
        for user in created_users:
            attendance_data.append({
                "employee_id": str(user.id),
                "timestamp": datetime.now(),
                "status": "check_in",
                "device_id": "BATCH_IMPORT"
            })
        
        attendance_records = DatabaseManager.bulk_create_records(AttendanceData, attendance_data)
        print(f"Created {len(attendance_records)} attendance records in batch")
    
    print("Batch operations completed - sync re-enabled")
    return created_users


def example_sync_control():
    """Example of manual sync control."""
    print("\n=== Sync Control Example ===")
    
    # Check sync status
    status = DatabaseManager.get_sync_status()
    print(f"Sync enabled: {status['sync_enabled']}")
    print(f"PostgreSQL connected: {status['postgres_connected']}")
    
    # Temporarily disable sync
    print("Disabling sync...")
    DatabaseManager.disable_sync()
    
    # Create user without sync
    user = create_user(
        first_name="Test",
        last_name="User",
        email="test.user@company.com",
        password_hash="test_hash",
        role="employee"
    )
    
    print(f"Created user without sync: {user.get_full_name()}")
    
    # Re-enable sync
    print("Re-enabling sync...")
    DatabaseManager.enable_sync()
    
    # Manually sync the user
    from sync_service import sync_model_to_postgres
    sync_model_to_postgres(user, 'insert')
    print(f"Manually synced user: {user.get_full_name()}")


def example_error_handling():
    """Example of error handling in database operations."""
    print("\n=== Error Handling Example ===")
    
    # Try to create user with duplicate email
    user1 = create_user(
        first_name="John",
        last_name="Duplicate",
        email="duplicate@company.com",
        password_hash="hash1",
        role="employee"
    )
    
    if user1:
        print(f"Created first user: {user1.get_full_name()}")
        
        # Try to create another user with same email
        user2 = create_user(
            first_name="Jane",
            last_name="Duplicate",
            email="duplicate@company.com",  # Same email - should fail
            password_hash="hash2",
            role="employee"
        )
        
        if user2:
            print(f"Created second user: {user2.get_full_name()}")
        else:
            print("Failed to create user with duplicate email (expected)")


def example_monitoring():
    """Example of monitoring sync status."""
    print("\n=== Monitoring Example ===")
    
    # Get detailed sync statistics
    if hasattr(sync_service, 'get_sync_stats'):
        stats = sync_service.get_sync_stats()
        print("Sync Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    # Test PostgreSQL connection
    postgres_ok = sync_service.test_postgres_connection()
    print(f"PostgreSQL connection: {'✓ OK' if postgres_ok else '✗ Failed'}")
    
    # Count records in both databases
    sqlite_user_count = db.session.query(User).count()
    print(f"SQLite user count: {sqlite_user_count}")
    
    try:
        with sync_service.get_postgres_session() as pg_session:
            postgres_user_count = pg_session.query(User).count()
            print(f"PostgreSQL user count: {postgres_user_count}")
            
            if sqlite_user_count == postgres_user_count:
                print("✓ Database counts match")
            else:
                print("⚠ Database counts don't match")
    except Exception as e:
        print(f"✗ Failed to check PostgreSQL: {str(e)}")


def main():
    """Main example function."""
    print("Dual Database Setup - Usage Examples")
    print("=" * 50)
    
    # Set up Flask app
    app = setup_app()
    
    with app.app_context():
        try:
            # Run examples
            user, department = example_basic_operations()
            batch_users = example_batch_operations()
            example_sync_control()
            example_error_handling()
            example_monitoring()
            
            print("\n" + "=" * 50)
            print("All examples completed successfully!")
            print("\nKey takeaways:")
            print("1. Use DatabaseManager or helper functions for automatic sync")
            print("2. Use BatchOperationContext for bulk operations")
            print("3. Monitor sync status with get_sync_status()")
            print("4. Handle errors gracefully - sync failures don't break main operations")
            print("5. Test PostgreSQL connection regularly")
            
        except Exception as e:
            print(f"\nError running examples: {str(e)}")
            print("Make sure PostgreSQL is accessible and configured correctly")


if __name__ == '__main__':
    main()

