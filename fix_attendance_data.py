#!/usr/bin/env python3
"""
Script to re-process attendance data for specific users and date ranges
This will fix the check-in/check-out times using the updated logic
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import User, DailyAttendance, AttendanceLog
from routes.attendance import process_daily_attendance
from datetime import datetime, date
from extensions import db

def fix_attendance_for_user_and_date_range(user_id, start_date, end_date):
    """Re-process attendance data for a specific user and date range"""
    
    app = create_app()
    with app.app_context():
        user = User.query.get(user_id)
        if not user:
            print(f"User with ID {user_id} not found")
            return
            
        print(f"Re-processing attendance data for {user.get_full_name()} from {start_date} to {end_date}")
        
        current_date = start_date
        processed_count = 0
        
        while current_date <= end_date:
            # Check if there are any logs for this date
            logs_count = AttendanceLog.query.filter(
                AttendanceLog.user_id == user_id,
                AttendanceLog.timestamp >= datetime.combine(current_date, datetime.min.time()),
                AttendanceLog.timestamp <= datetime.combine(current_date, datetime.max.time())
            ).count()
            
            if logs_count > 0:
                print(f"  Processing {current_date} ({logs_count} logs)...")
                
                # Delete existing DailyAttendance record if it exists
                existing_record = DailyAttendance.query.filter_by(
                    user_id=user_id,
                    date=current_date
                ).first()
                
                if existing_record:
                    db.session.delete(existing_record)
                    db.session.commit()
                
                # Re-process the attendance for this date
                new_record = process_daily_attendance(user_id, current_date)
                
                if new_record:
                    db.session.commit()
                    print(f"    ✓ Updated: Check-in: {new_record.first_check_in}, Check-out: {new_record.last_check_out}")
                    processed_count += 1
                else:
                    print(f"    ✗ Failed to process {current_date}")
            
            current_date = current_date.replace(day=current_date.day + 1) if current_date.day < 31 else current_date.replace(month=current_date.month + 1, day=1)
            
        print(f"Completed! Processed {processed_count} days for {user.get_full_name()}")

if __name__ == "__main__":
    # Fix attendance for Youssef George (assuming user_id = 3 based on the report)
    # You can modify these values as needed
    
    user_id = 3  # Youssef George's user ID
    start_date = date(2025, 9, 25)
    end_date = date(2025, 10, 22)
    
    print("Starting attendance data fix...")
    fix_attendance_for_user_and_date_range(user_id, start_date, end_date)
    print("Done!")
