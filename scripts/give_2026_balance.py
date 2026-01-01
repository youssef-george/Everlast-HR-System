#!/usr/bin/env python3
"""
Script to give every employee who doesn't have a 2026 balance 1 day
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, User, LeaveType, LeaveBalance
from datetime import datetime

def give_2026_balance():
    """Give every employee without a 2026 balance 1 day"""
    app = create_app()
    
    with app.app_context():
        try:
            # Get or find Annual Leave type
            annual_leave_type = LeaveType.query.filter(
                db.func.lower(LeaveType.name) == 'annual'
            ).first()
            
            if not annual_leave_type:
                # Try alternative names
                annual_leave_type = LeaveType.query.filter(
                    db.func.lower(LeaveType.name).like('%annual%')
                ).first()
            
            if not annual_leave_type:
                # Try exact match
                annual_leave_type = LeaveType.query.filter_by(name='Annual Leave').first()
            
            if not annual_leave_type:
                # Create Annual Leave type if it doesn't exist
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
            
            target_year = 2026
            created_count = 0
            skipped_count = 0
            
            for employee in active_employees:
                # Check if balance already exists for 2026
                existing_balance = LeaveBalance.query.filter_by(
                    user_id=employee.id,
                    leave_type_id=annual_leave_type.id,
                    year=target_year
                ).first()
                
                if existing_balance:
                    # Employee already has a 2026 balance, skip
                    skipped_count += 1
                    print(f"Skipped {employee.get_full_name()} - already has 2026 balance")
                else:
                    # Create new balance with 1 day
                    balance = LeaveBalance(
                        user_id=employee.id,
                        leave_type_id=annual_leave_type.id,
                        total_days=1,
                        used_days=0,
                        remaining_days=1,
                        year=target_year
                    )
                    db.session.add(balance)
                    created_count += 1
                    print(f"Created 1 day balance for {employee.get_full_name()} (2026)")
            
            db.session.commit()
            
            print(f"\n2026 balance assignment completed!")
            print(f"Created balances: {created_count} employees")
            print(f"Skipped (already have balance): {skipped_count} employees")
            print(f"Total processed: {len(active_employees)} employees")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error assigning 2026 balances: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        return True

if __name__ == '__main__':
    print("Giving 1 day 2026 balance to employees without one...")
    success = give_2026_balance()
    
    if success:
        print("\n2026 balance assignment completed successfully!")
    else:
        print("\n2026 balance assignment failed!")
        sys.exit(1)

