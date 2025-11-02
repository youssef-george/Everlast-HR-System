import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, LeaveRequest, User

def list_leave_requests():
    app = create_app()
    with app.app_context():
        try:
            leave_requests = LeaveRequest.query.all()
            if not leave_requests:
                print("No leave requests found in the database.")
                return

            print(f"Found {len(leave_requests)} leave requests:")
            for lr in leave_requests:
                user = User.query.get(lr.user_id)
                user_info = f"{user.first_name} {user.last_name}" if user else "Unknown User"
                print(f"  ID: {lr.id}, User: {user_info}, Type: {lr.leave_type.name if lr.leave_type else 'N/A'}, Start: {lr.start_date}, End: {lr.end_date}, Status: {lr.status}")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    list_leave_requests()