#!/usr/bin/env python3
"""
Script to initialize leave balances for all active employees
This script sets up Annual Leave balances with 21 total days and 10 remaining days
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, User, LeaveType, LeaveBalance
from datetime import datetime

def initialize_leave_balances():
    """Initialize leave balances for all active employees"""
    app = create_app()
    
    with app.app_context():
        try:
            # Get or create Annual Leave type
            annual_leave_type = LeaveType.query.filter_by(name='Annual Leave').first()
            if not annual_leave_type:
                annual_leave_type = LeaveType(
                    name='Annual Leave',
                    description='Annual vacation leave',
                    color='#28a745',
                    is_active=True,
                    requires_balance=True
                )
                db.session.add(annual_leave_type)
                db.session.commit()
                print("Created Annual Leave type")
            
            # Get all active employees
            active_employees = User.query.filter_by(status='active').all()
            print(f"Found {len(active_employees)} active employees")
            
            current_year = datetime.now().year
            initialized_count = 0
            updated_count = 0
            
            for employee in active_employees:
                # Check if balance already exists for this year
                existing_balance = LeaveBalance.query.filter_by(
                    user_id=employee.id,
                    leave_type_id=annual_leave_type.id,
                    year=current_year
                ).first()
                
                if existing_balance:
                    # Update existing balance
                    existing_balance.total_days = 21
                    existing_balance.used_days = max(0, 21 - 10)  # 11 used days
                    existing_balance.remaining_days = 10
                    updated_count += 1
                    print(f"Updated balance for {employee.get_full_name()}")
                else:
                    # Create new balance
                    balance = LeaveBalance(
                        user_id=employee.id,
                        leave_type_id=annual_leave_type.id,
                        total_days=21,
                        used_days=11,  # 21 - 10 = 11 used
                        remaining_days=10,
                        year=current_year
                    )
                    db.session.add(balance)
                    initialized_count += 1
                    print(f"Created balance for {employee.get_full_name()}")
            
            db.session.commit()
            
            print(f"\nLeave balance initialization completed!")
            print(f"Initialized: {initialized_count} employees")
            print(f"Updated: {updated_count} employees")
            print(f"Total processed: {initialized_count + updated_count} employees")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error initializing leave balances: {str(e)}")
            return False
        
        return True

if __name__ == '__main__':
    print("Initializing leave balances for active employees...")
    success = initialize_leave_balances()
    
    if success:
        print("Leave balance initialization completed successfully!")
    else:
        print("Leave balance initialization failed!")
        sys.exit(1)
