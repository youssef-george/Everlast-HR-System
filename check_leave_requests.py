#!/usr/bin/env python3
"""
Script to check and clean leave requests in the database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, LeaveRequest, User

def check_leave_requests():
    """Check and clean leave requests in the database"""
    app = create_app()
    
    with app.app_context():
        try:
            # Get all leave requests
            leave_requests = LeaveRequest.query.all()
            print(f"Found {len(leave_requests)} leave requests in the database")
            
            for i, leave in enumerate(leave_requests):
                print(f"\nLeave Request {i+1}:")
                print(f"  ID: {leave.id}")
                print(f"  User ID: {leave.user_id}")
                print(f"  Start Date: {leave.start_date}")
                print(f"  End Date: {leave.end_date}")
                print(f"  Reason: {leave.reason}")
                print(f"  Status: {leave.status}")
                print(f"  Created At: {leave.created_at}")
                
                # Check if user exists
                user = User.query.get(leave.user_id)
                if user:
                    print(f"  User: {user.first_name} {user.last_name}")
                else:
                    print(f"  User: NOT FOUND (ID: {leave.user_id})")
            
            # Ask if user wants to delete all
            if leave_requests:
                confirm = input(f"\nDo you want to delete all {len(leave_requests)} leave requests? (yes/no): ")
                if confirm.lower() == 'yes':
                    LeaveRequest.query.delete()
                    db.session.commit()
                    print("All leave requests deleted successfully")
                else:
                    print("No changes made")
            else:
                print("No leave requests found")
                
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            db.session.rollback()
            return False
    
    return True

if __name__ == "__main__":
    print("Leave Request Database Check")
    print("=" * 40)
    check_leave_requests()




