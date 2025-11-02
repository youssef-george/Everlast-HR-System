#!/usr/bin/env python3
"""
Script to fix existing manager leave requests that were created before the fix
This script sets manager_status to 'approved' for all leave requests submitted by managers
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, LeaveRequest, User

def fix_manager_leave_requests():
    """Fix existing manager leave requests"""
    app = create_app()
    
    with app.app_context():
        try:
            # Find all leave requests submitted by managers that still have pending manager status
            manager_leave_requests = LeaveRequest.query.join(User).filter(
                User.role == 'manager',
                LeaveRequest.manager_status == 'pending'
            ).all()
            
            print(f"Found {len(manager_leave_requests)} manager leave requests to fix")
            
            fixed_count = 0
            for leave_request in manager_leave_requests:
                print(f"Fixing leave request {leave_request.id} for {leave_request.user.get_full_name()}")
                leave_request.manager_status = 'approved'
                leave_request.update_overall_status()
                fixed_count += 1
            
            db.session.commit()
            
            print(f"\nFixed {fixed_count} manager leave requests!")
            print("All manager leave requests now have manager_status = 'approved'")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error fixing manager leave requests: {str(e)}")
            return False
        
        return True

if __name__ == '__main__':
    print("Fixing manager leave requests...")
    success = fix_manager_leave_requests()
    
    if success:
        print("Manager leave request fix completed successfully!")
    else:
        print("Manager leave request fix failed!")
        sys.exit(1)
