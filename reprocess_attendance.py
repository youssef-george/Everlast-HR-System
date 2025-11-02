#!/usr/bin/env python3
"""
Simple script to re-process attendance data
"""

from flask import Flask
from datetime import datetime, date, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Import after setting up logging
from app import create_app

def reprocess_attendance():
    """Re-process attendance data for recent dates"""
    
    app = create_app()
    
    with app.app_context():
        from models import User, DailyAttendance, AttendanceLog
        from routes.attendance import process_daily_attendance
        from extensions import db
        
        print("Looking for users...")
        
        # Find all active users
        users = User.query.filter_by(status='active').all()
        print(f"Found {len(users)} active users")
        
        for user in users:
            print(f"User: {user.first_name} {user.last_name} (ID: {user.id})")
        
        # Find Youssef George specifically
        youssef = None
        for user in users:
            if 'youssef' in user.first_name.lower() or 'george' in user.last_name.lower():
                youssef = user
                break
        
        if not youssef:
            print("Youssef George not found, processing all users with recent attendance...")
            # Process all users for the last month
            start_date = date(2025, 9, 25)
            end_date = date(2025, 10, 22)
            
            for user in users:
                print(f"\nProcessing user: {user.first_name} {user.last_name}")
                reprocess_user_attendance(user.id, start_date, end_date)
        else:
            print(f"\nFound Youssef: {youssef.first_name} {youssef.last_name} (ID: {youssef.id})")
            start_date = date(2025, 9, 25)
            end_date = date(2025, 10, 22)
            reprocess_user_attendance(youssef.id, start_date, end_date)

def reprocess_user_attendance(user_id, start_date, end_date):
    """Re-process attendance for a specific user"""
    from models import DailyAttendance, AttendanceLog
    from routes.attendance import process_daily_attendance
    from extensions import db
    
    current_date = start_date
    processed = 0
    
    while current_date <= end_date:
        # Check if there are logs for this date
        start_datetime = datetime.combine(current_date, datetime.min.time())
        end_datetime = datetime.combine(current_date, datetime.max.time())
        
        logs = AttendanceLog.query.filter(
            AttendanceLog.user_id == user_id,
            AttendanceLog.timestamp.between(start_datetime, end_datetime)
        ).all()
        
        if logs:
            print(f"  {current_date}: {len(logs)} logs found")
            
            # Delete existing record
            existing = DailyAttendance.query.filter_by(
                user_id=user_id,
                date=current_date
            ).first()
            
            if existing:
                db.session.delete(existing)
                db.session.flush()
            
            # Re-process
            try:
                new_record = process_daily_attendance(user_id, current_date)
                if new_record:
                    db.session.commit()
                    print(f"    ✓ Check-in: {new_record.first_check_in}, Check-out: {new_record.last_check_out}")
                    processed += 1
                else:
                    print(f"    ✗ Failed to create record")
            except Exception as e:
                print(f"    ✗ Error: {e}")
                db.session.rollback()
        
        current_date += timedelta(days=1)
    
    print(f"  Processed {processed} days")

if __name__ == "__main__":
    reprocess_attendance()
