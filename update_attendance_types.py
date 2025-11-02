from flask import Flask
from routes.attendance import determine_attendance_type, AttendanceLog, process_daily_attendance
from models import db
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///everlast.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Update attendance types
with app.app_context():
    try:
        # Get today's records
        today = datetime.now().date()
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today, datetime.max.time())
        
        # Get all records for today
        records = AttendanceLog.query.filter(
            AttendanceLog.timestamp.between(start_datetime, end_datetime)
        ).order_by(AttendanceLog.timestamp).all()
        
        logging.info(f"Found {len(records)} records for today")
        
        # Group records by user
        user_records = {}
        for record in records:
            if record.user_id not in user_records:
                user_records[record.user_id] = []
            user_records[record.user_id].append(record)
        
        # Process each user's records
        for user_id, user_logs in user_records.items():
            try:
                # Sort records by timestamp
                user_logs.sort(key=lambda x: x.timestamp)
                
                # Update scan types based on sequence
                updates = 0
                first_record = True
                
                for record in user_logs:
                    # First record of the day should be check-in unless it's after 5 PM
                    if first_record:
                        new_type = 'check-out' if record.timestamp.hour >= 17 else 'check-in'
                        first_record = False
                    else:
                        new_type = determine_attendance_type(record.timestamp)
                    
                    if new_type != record.scan_type:
                        old_type = record.scan_type
                        record.scan_type = new_type
                        updates += 1
                        logging.info(f"Updated record for {record.user.get_full_name()} at {record.timestamp.strftime('%I:%M:%S %p')} from {old_type} to {new_type}")
                
                if updates > 0:
                    db.session.commit()
                    logging.info(f"Updated {updates} records for user {user_id}")
                
                # Recalculate daily attendance
                daily_record = process_daily_attendance(user_id, today)
                if daily_record:
                    db.session.commit()
                    logging.info(f"Updated daily attendance for user {user_id}")
                    logging.info(f"Status: {daily_record.status}, Hours: {daily_record.total_working_hours}")
                
            except Exception as e:
                logging.error(f"Error processing records for user {user_id}: {str(e)}")
                db.session.rollback()
                continue
        
        logging.info("Finished processing all records")
            
    except Exception as e:
        logging.error(f"Error updating attendance types: {str(e)}")
        db.session.rollback() 