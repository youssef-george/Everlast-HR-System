#!/usr/bin/env python3
"""
Script to set up default leave types with proper requires_balance settings
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, LeaveType

def setup_leave_types():
    """Set up default leave types with proper balance requirements"""
    app = create_app()
    
    with app.app_context():
        # Define default leave types
        leave_types = [
            {
                'name': 'Annual Leave',
                'description': 'Regular annual vacation leave',
                'color': '#007bff',
                'requires_balance': True
            },
            {
                'name': 'Sick Leave',
                'description': 'Medical leave for illness',
                'color': '#dc3545',
                'requires_balance': True
            },
            {
                'name': 'Unpaid Leave',
                'description': 'Leave without pay',
                'color': '#6c757d',
                'requires_balance': False
            },
            {
                'name': 'Personal Leave',
                'description': 'Personal time off',
                'color': '#28a745',
                'requires_balance': True
            },
            {
                'name': 'Emergency Leave',
                'description': 'Emergency situations',
                'color': '#ffc107',
                'requires_balance': False
            },
            {
                'name': 'Maternity Leave',
                'description': 'Maternity leave',
                'color': '#e83e8c',
                'requires_balance': False
            },
            {
                'name': 'Paternity Leave',
                'description': 'Paternity leave',
                'color': '#17a2b8',
                'requires_balance': False
            }
        ]
        
        created_count = 0
        updated_count = 0
        
        for lt_data in leave_types:
            # Check if leave type already exists
            existing = LeaveType.query.filter_by(name=lt_data['name']).first()
            
            if existing:
                # Update existing leave type
                existing.description = lt_data['description']
                existing.color = lt_data['color']
                existing.requires_balance = lt_data['requires_balance']
                updated_count += 1
                print(f"Updated leave type: {lt_data['name']} (requires_balance: {lt_data['requires_balance']})")
            else:
                # Create new leave type
                leave_type = LeaveType(
                    name=lt_data['name'],
                    description=lt_data['description'],
                    color=lt_data['color'],
                    requires_balance=lt_data['requires_balance']
                )
                db.session.add(leave_type)
                created_count += 1
                print(f"Created leave type: {lt_data['name']} (requires_balance: {lt_data['requires_balance']})")
        
        try:
            db.session.commit()
            print(f"\n✅ Successfully processed {created_count + updated_count} leave types:")
            print(f"   - Created: {created_count}")
            print(f"   - Updated: {updated_count}")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error setting up leave types: {str(e)}")
            return False
        
        return True

if __name__ == '__main__':
    print("Setting up leave types with balance requirements...")
    success = setup_leave_types()
    if success:
        print("\n🎉 Leave types setup completed successfully!")
    else:
        print("\n💥 Leave types setup failed!")
        sys.exit(1)
