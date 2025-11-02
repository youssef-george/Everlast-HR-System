from flask import Flask
from routes.attendance import sync_attendance_task, AttendanceLog
from models import db
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///everlast.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Run sync task
with app.app_context():
    try:
        logging.info("Starting manual sync...")
        sync_attendance_task()
        logging.info("Sync completed")
        
        # Get latest records from the last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        latest_logs = AttendanceLog.query.filter(
            AttendanceLog.timestamp >= one_hour_ago
        ).order_by(AttendanceLog.timestamp.desc()).all()
        
        if latest_logs:
            logging.info(f"\nLatest records in the last hour:")
            for log in latest_logs:
                logging.info(f"{log.user.get_full_name()} - {log.scan_type} at {log.timestamp.strftime('%I:%M:%S %p')}")
        else:
            logging.info("No new records found in the last hour")
    except Exception as e:
        logging.error(f"Sync failed: {str(e)}") 