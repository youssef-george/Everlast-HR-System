"""
Database Helper Functions
Provides convenient functions for database operations.
"""

import logging
from typing import Any, Dict, List, Optional, Type
from flask import current_app
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from extensions import db

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations."""
    
    @staticmethod
    def create_record(model_class: Type[db.Model], **kwargs) -> Optional[db.Model]:
        """
        Create a new record.
        
        Args:
            model_class: SQLAlchemy model class
            **kwargs: Field values for the new record
            
        Returns:
            Created model instance or None if failed
        """
        try:
            # Create new record
            record = model_class(**kwargs)
            db.session.add(record)
            db.session.commit()
            
            logger.info(f"Created {model_class.__tablename__} record with ID {record.id}")
            return record
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create {model_class.__tablename__} record: {str(e)}")
            return None
    
    @staticmethod
    def update_record(record: db.Model, **kwargs) -> bool:
        """
        Update an existing record.
        
        Args:
            record: Model instance to update
            **kwargs: Field values to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update fields
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            
            db.session.commit()
            
            logger.info(f"Updated {record.__class__.__tablename__} record with ID {record.id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update {record.__class__.__tablename__} record: {str(e)}")
            return False
    
    @staticmethod
    def delete_record(record: db.Model) -> bool:
        """
        Delete a record.
        
        Args:
            record: Model instance to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            record_id = record.id
            table_name = record.__class__.__tablename__
            
            db.session.delete(record)
            db.session.commit()
            
            logger.info(f"Deleted {table_name} record with ID {record_id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete {record.__class__.__tablename__} record: {str(e)}")
            return False
    
    @staticmethod
    def bulk_create_records(model_class: Type[db.Model], records_data: List[Dict[str, Any]]) -> List[db.Model]:
        """
        Create multiple records.
        
        Args:
            model_class: SQLAlchemy model class
            records_data: List of dictionaries containing field values
            
        Returns:
            List of created model instances
        """
        created_records = []
        
        try:
            for record_data in records_data:
                record = model_class(**record_data)
                db.session.add(record)
                created_records.append(record)
            
            db.session.commit()
            
            logger.info(f"Created {len(created_records)} {model_class.__tablename__} records")
            return created_records
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to bulk create {model_class.__tablename__} records: {str(e)}")
            return []
    
    @staticmethod
    def bulk_update_records(model_class: Type[db.Model], updates: List[Dict[str, Any]]) -> int:
        """
        Update multiple records.
        
        Args:
            model_class: SQLAlchemy model class
            updates: List of dictionaries with 'id' and field values to update
            
        Returns:
            Number of successfully updated records
        """
        updated_count = 0
        
        for update_data in updates:
            record_id = update_data.pop('id', None)
            if not record_id:
                continue
            
            try:
                record = db.session.query(model_class).filter_by(id=record_id).first()
                if record:
                    if DatabaseManager.update_record(record, **update_data):
                        updated_count += 1
                        
            except Exception as e:
                logger.error(f"Failed to update record {record_id}: {str(e)}")
        
        logger.info(f"Updated {updated_count}/{len(updates)} {model_class.__tablename__} records")
        return updated_count
    


# Convenience functions for common operations
def create_user(**kwargs):
    """Create a new user."""
    from models import User
    return DatabaseManager.create_record(User, **kwargs)


def update_user(user, **kwargs):
    """Update a user."""
    return DatabaseManager.update_record(user, **kwargs)


def delete_user(user):
    """Delete a user."""
    return DatabaseManager.delete_record(user)


def create_attendance_record(**kwargs):
    """Create an attendance record."""
    from models import AttendanceData
    return DatabaseManager.create_record(AttendanceData, **kwargs)


def create_leave_request(**kwargs):
    """Create a leave request."""
    from models import LeaveRequest
    return DatabaseManager.create_record(LeaveRequest, **kwargs)


def update_leave_request(leave_request, **kwargs):
    """Update a leave request."""
    return DatabaseManager.update_record(leave_request, **kwargs)


def create_permission_request(**kwargs):
    """Create a permission request."""
    from models import PermissionRequest
    return DatabaseManager.create_record(PermissionRequest, **kwargs)


def update_permission_request(permission_request, **kwargs):
    """Update a permission request."""
    return DatabaseManager.update_record(permission_request, **kwargs)


# Example usage functions
def example_create_user():
    """Example of creating a user."""
    user = create_user(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        password_hash="hashed_password",
        role="employee"
    )
    
    if user:
        print(f"User created with ID: {user.id}")
        return user
    else:
        print("Failed to create user")
        return None


def example_batch_operation():
    """Example of batch operation."""
    users_data = [
        {"first_name": "Alice", "last_name": "Smith", "email": "alice@example.com", "password_hash": "hash1", "role": "employee"},
        {"first_name": "Bob", "last_name": "Johnson", "email": "bob@example.com", "password_hash": "hash2", "role": "employee"},
        {"first_name": "Carol", "last_name": "Williams", "email": "carol@example.com", "password_hash": "hash3", "role": "manager"}
    ]
    
    from models import User
    created_users = DatabaseManager.bulk_create_records(User, users_data)
    print(f"Created {len(created_users)} users in batch")
    print("Batch operation completed")


if __name__ == "__main__":
    # Example usage (requires Flask app context)
    print("Database helpers module loaded successfully")
    print("Available functions:")
    print("- DatabaseManager class for advanced operations")
    print("- create_user(), update_user(), delete_user()")
    print("- create_attendance_record()")
    print("- create_leave_request(), update_leave_request()")
    print("- create_permission_request(), update_permission_request()")
