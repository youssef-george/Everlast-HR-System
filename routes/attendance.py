from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, abort
# from flask_apscheduler import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED  # Not needed anymore
from flask_login import login_required, current_user
from models import db, User, AttendanceLog, DailyAttendance, LeaveRequest, PermissionRequest, FingerPrintFailure, DeviceSettings, DeviceUser
from sqlalchemy import or_, and_, func
from helpers import role_required, sync_users_from_device
from forms import DeviceSettingsForm
from datetime import datetime, timedelta, date
from zk import ZK
import logging
from collections import defaultdict, OrderedDict
import socket
import time
import threading
import json
import subprocess
import platform
from utils import convert_utc_to_local
from flask import current_app as app

attendance_bp = Blueprint('attendance', __name__, url_prefix='/attendance')

# Add datetime context processor
@attendance_bp.context_processor
def inject_datetime():
    return {
        'now': datetime.now(),
        'today': date.today()
    }

# Global lock for sync operations
sync_lock = threading.Lock()

def protect_admin_routes():
    """Protect admin-only attendance routes"""
    # Routes that should be excluded from IS_ADMIN_INSTANCE check
    # (they have their own role-based access control)
    excluded_routes = [
        'attendance.my_attendance',
        'attendance.my_attendance_sync_status',
        'attendance.index',
        'attendance.device_settings',  # Has @role_required(['admin', 'product_owner'])
    ]
    
    if (request.endpoint 
        and request.endpoint.startswith('attendance.') 
        and request.endpoint not in excluded_routes
        and not current_app.config.get('IS_ADMIN_INSTANCE', False)):
        flash('This feature is only available on the admin portal.', 'error')
        return redirect(url_for('dashboard.index'))

# Apply protection to admin routes
@attendance_bp.before_request
def before_request():
    # Skip protection for excluded routes
    excluded_routes = [
        'attendance.my_attendance',
        'attendance.my_attendance_sync_status',
        'attendance.index',
        'attendance.device_settings',  # Has its own role-based access control
    ]
    if request.endpoint in excluded_routes:
        return None
    return protect_admin_routes()

def format_duration(duration):
    """Format timedelta into hours and minutes"""
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def safe_db_query(query_func, default=None):
    """Execute a database query with automatic rollback on error"""
    try:
        return query_func()
    except Exception as e:
        # Check if it's a transaction error
        error_str = str(e).lower()
        if 'infailedsqltransaction' in error_str or 'transaction is aborted' in error_str:
            logging.warning(f"Transaction aborted, rolling back: {e}")
            try:
                db.session.rollback()
            except Exception as rollback_error:
                logging.error(f"Error during rollback: {rollback_error}")
        else:
            logging.error(f"Database query error: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
        return default

def cleanup_orphaned_paid_holiday_records():
    """Remove DailyAttendance records that reference deleted paid holidays"""
    try:
        from models import PaidHoliday
        
        # Find all DailyAttendance records with paid_holiday_id that don't exist in PaidHoliday table
        orphaned_records = safe_db_query(
            lambda: DailyAttendance.query.filter(
            DailyAttendance.paid_holiday_id.isnot(None),
            ~DailyAttendance.paid_holiday_id.in_(
                db.session.query(PaidHoliday.id)
            )
            ).all(),
            default=[]
        )
        
        # Find all DailyAttendance records with paid_holiday status but no paid_holiday_id
        orphaned_status_records = safe_db_query(
            lambda: DailyAttendance.query.filter(
            DailyAttendance.paid_holiday_id.is_(None),
            DailyAttendance.status == 'paid_holiday'
            ).all(),
            default=[]
        )
        
        total_orphaned = len(orphaned_records) + len(orphaned_status_records)
        
        if total_orphaned > 0:
            logging.info(f"Found {len(orphaned_records)} orphaned paid holiday records with paid_holiday_id")
            logging.info(f"Found {len(orphaned_status_records)} orphaned paid holiday records with paid_holiday status")
            
            try:
                for record in orphaned_records:
                    db.session.delete(record)
                
                for record in orphaned_status_records:
                    db.session.delete(record)
                
                db.session.commit()
                logging.info(f"Cleaned up {total_orphaned} orphaned paid holiday records")
            except Exception as e:
                logging.error(f"Error committing orphaned record cleanup: {str(e)}")
                db.session.rollback()
        
    except Exception as e:
        logging.error(f"Error cleaning up orphaned paid holiday records: {str(e)}")
        try:
            db.session.rollback()
        except Exception:
            pass

def determine_attendance_type(timestamp):
    """Simple fallback for legacy code - determines type based on time of day"""
    hour = timestamp.hour
    # Simple rule: before 2 PM is check-in, after 2 PM is check-out
    return 'check-in' if hour < 14 else 'check-out'

def determine_attendance_type_dynamic(logs_for_user):
    """Determine check-in/check-out dynamically based on timestamps only
    
    Business Rules for Incomplete Days:
    1. ONLY 1 log entry total: Mark as incomplete, assign 9 hours for past dates
    2. Multiple log entries (even with same timestamp): Mark as complete, calculate actual hours
    3. No logs: Mark as absent (not incomplete)
    
    FIXED: Days with 10+ logs should NEVER be marked as incomplete
    
    Args:
        logs_for_user: List of logs for a single user on a single day
    
    Returns:
        dict: {'check_in': earliest_log, 'check_out': latest_log, 'is_incomplete': bool}
    """
    if not logs_for_user:
        return {'check_in': None, 'check_out': None, 'is_incomplete': False}

    # Sort all logs by timestamp to ensure proper order
    all_logs = sorted(logs_for_user, key=lambda x: x.timestamp)
    
    # ALWAYS use first log as check-in and last log as check-out
    first_log = all_logs[0]
    last_log = all_logs[-1]
    
    # Only mark as incomplete if there is exactly 1 log entry
    total_log_count = len(logs_for_user)
    
    if total_log_count == 1:
        # Only 1 log entry total = incomplete day
        return {
            'check_in': first_log,
            'check_out': None,
            'is_incomplete': True
        }
    else:
        # Multiple logs = complete day, use first and last logs
        return {
            'check_in': first_log,
            'check_out': last_log,
            'is_incomplete': False
        }

def process_attendance_logs(logs):
    """Process attendance logs to group by user and determine check-in/check-out using dynamic logic"""
    user_logs = {}
    
    # Group logs by user
    for log in logs:
        if log.user_id not in user_logs:
            user_logs[log.user_id] = {
                'user': log.user,
                'check_in': None,
                'check_out': None,
                'duration': None,
                'status': 'absent',  # Default status
                'all_logs': [],  # Store all logs for this user
                'is_incomplete': False
            }
        user_logs[log.user_id]['all_logs'].append(log)
    
    # Process each user's logs using dynamic logic
    for user_id, data in user_logs.items():
        attendance_result = determine_attendance_type_dynamic(data['all_logs'])
        
        data['check_in'] = attendance_result['check_in']
        data['check_out'] = attendance_result['check_out']
        data['is_incomplete'] = attendance_result['is_incomplete']
        
        # Determine status based on logs
        if data['check_in'] and data['check_out']:
            # Complete day with both check-in and check-out
            duration = data['check_out'].timestamp - data['check_in'].timestamp
            data['duration'] = format_duration(duration)
            data['status'] = 'present'
        elif data['check_in'] and not data['check_out']:
            # Incomplete day - single log
            data['status'] = 'present'  # Still count as present
            data['duration'] = None
        else:
            # No logs (shouldn't happen in this function, but safety check)
            data['status'] = 'absent'
    
    return user_logs

def calculate_working_hours(check_in, check_out):
    """Calculate working hours between check-in and check-out"""
    if not check_in or not check_out:
        return 0.0
    
    duration = check_out - check_in
    hours = duration.total_seconds() / 3600
    return round(hours, 2)

def update_daily_attendance(user_id, attendance_date, check_in=None, check_out=None):
    """Update or create daily attendance record"""
    daily_record = DailyAttendance.query.filter_by(
        user_id=user_id,
        date=attendance_date
    ).first()
    
    if not daily_record:
        daily_record = DailyAttendance(
            user_id=user_id,
            date=attendance_date
        )
        db.session.add(daily_record)
    
    # Update check-in if it's earlier than existing or if there's no existing check-in
    if check_in and (not daily_record.first_check_in or check_in < daily_record.first_check_in):
        daily_record.first_check_in = check_in
    
    # Update check-out if it's later than existing or if there's no existing check-out
    if check_out and (not daily_record.last_check_out or check_out > daily_record.last_check_out):
        daily_record.last_check_out = check_out
    
    # Calculate total working hours if both check-in and check-out exist
    if daily_record.first_check_in and daily_record.last_check_out:
        daily_record.total_working_hours = calculate_working_hours(
            daily_record.first_check_in,
            daily_record.last_check_out
        )
        
        # Update status based on working hours - standard workday is 9 hours
        if daily_record.total_working_hours >= 4.5:
            daily_record.status = 'present'  # Changed: half-day is now treated as present
        else:
            daily_record.status = 'partial'
    
    db.session.commit()
    return daily_record

def process_daily_attendance(user_id, attendance_date):
    """Process all attendance logs for a user on a specific date"""
    # Get all logs for this user on this date, ordered by timestamp
    start_of_day = datetime.combine(attendance_date, datetime.min.time())
    end_of_day = datetime.combine(attendance_date, datetime.max.time())
    daily_logs = AttendanceLog.query.filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.timestamp.between(start_of_day, end_of_day)
    ).order_by(AttendanceLog.timestamp).all()

    user = User.query.get(user_id)
    if user and user.joining_date and attendance_date < user.joining_date:
        # If the attendance date is before the user's joining date, ignore it
        return None

    if not daily_logs:
        return None

    # Initialize scan_order and update existing logs
    for i, log in enumerate(daily_logs):
        log.scan_order = i + 1
        log.is_extra_scan = (i + 1) > 2  # Mark as extra scan if it's the 3rd or subsequent scan
        db.session.add(log) # Add to session to ensure updates are tracked

    # Commit the changes to scan_order and is_extra_scan
    db.session.commit()
    
    # Check if this date is a paid holiday
    from models import PaidHoliday
    paid_holiday = PaidHoliday.query.filter(
        or_(
            # Single day holiday
            and_(PaidHoliday.holiday_type == 'day',
                 PaidHoliday.start_date == attendance_date),
            # Range holiday that includes this date
            and_(PaidHoliday.holiday_type == 'range',
                 PaidHoliday.start_date <= attendance_date,
                 PaidHoliday.end_date >= attendance_date)
        )
    ).first()
    
    # Get leave/permission requests for this date
    leave_request = LeaveRequest.query.filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.start_date <= attendance_date,
        LeaveRequest.end_date >= attendance_date,
        LeaveRequest.status == 'approved'
    ).first()
    
    permission_request = PermissionRequest.query.filter(
        PermissionRequest.user_id == user_id,
        func.date(PermissionRequest.start_time) == attendance_date,
        PermissionRequest.status == 'approved'
    ).first()
    
    # Use dynamic attendance processing - first log = check-in, last log = check-out
    attendance_result = determine_attendance_type_dynamic(daily_logs)

    logging.debug(f"[ATTENDANCE_DEBUG] determine_attendance_type_dynamic returned: {attendance_result}")

    first_check_in = attendance_result['check_in'].timestamp if attendance_result['check_in'] else None
    last_check_out = attendance_result['check_out'].timestamp if attendance_result['check_out'] else None
    is_incomplete_day = attendance_result['is_incomplete']

    logging.debug(f"[ATTENDANCE_DEBUG] After assignment from attendance_result: First Check-in: {first_check_in}, Last Check-out: {last_check_out}, Incomplete: {is_incomplete_day}")
    
    # Calculate working hours based on FIXED business rules
    total_working_minutes = 0
    if first_check_in and last_check_out and first_check_in != last_check_out:
        # Multiple unique logs: calculate actual hours between first and last log
        duration_seconds = (last_check_out - first_check_in).total_seconds()
        total_working_minutes = int(duration_seconds / 60)
    elif first_check_in and last_check_out and first_check_in == last_check_out:
        # Multiple logs but same timestamp: assign 9 hours (user was present)
        total_working_minutes = 9 * 60  # 9 hours in minutes
    elif is_incomplete_day:
        # Single log: assign 9 hours as per requirements
        total_working_minutes = 9 * 60  # 9 hours in minutes
    
    # Deduct permission time from working hours if it overlaps with working time
    if permission_request and first_check_in and last_check_out:
        # Check if permission time overlaps with working hours
        permission_start = permission_request.start_time
        permission_end = permission_request.end_time
        
        # Find overlap between permission time and working time
        overlap_start = max(permission_start, first_check_in)
        overlap_end = min(permission_end, last_check_out)
        
        if overlap_start < overlap_end:
            # There's an overlap, deduct the permission time from working hours
            permission_minutes = int((overlap_end - overlap_start).total_seconds() / 60)
            total_working_minutes = max(0, total_working_minutes - permission_minutes)
    
    # Determine status and reason with proper priority
    status = 'absent'
    status_reason = None
    
    # Check if user has attendance logs - any log counts
    has_attendance_logs = len(daily_logs) > 0
    
    if paid_holiday:
        # Paid holiday logic
        if has_attendance_logs:
            status = 'present'
            status_reason = f"Present - Paid Leave - {paid_holiday.description}"
        else:
            status = 'paid_leave'
            status_reason = f"Paid Leave - {paid_holiday.description}"
    elif leave_request:
        # Leave request logic - always show as leave, don't hide attendance
        status = 'leave'
        status_reason = f"Approved Leave: {leave_request.reason[:50]}..."
    elif permission_request:
        # Permission request logic - show attendance if present, add permission as annotation
        if has_attendance_logs:
            status = 'present'
            duration = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
            status_reason = f"Present (Permission: {duration:.1f}h) - {permission_request.reason[:30]}..."
        else:
            status = 'permission'
            duration = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
            status_reason = f"Approved Permission ({duration:.1f}h): {permission_request.reason[:30]}..."
    elif has_attendance_logs:
        # User has attendance logs - ALWAYS mark as present (core rule)
        status = 'present'
        
        # Set appropriate status reason based on log type
        if is_incomplete_day:
            # Single log case: treat as present with 9 working hours
            status_reason = "Present (Single log - 9 hours assigned)"
        elif first_check_in and last_check_out:
            # Complete day with both check-in and check-out
            total_hours = total_working_minutes / 60
            if total_hours >= 4:
                status_reason = f"Present ({total_hours:.1f} hours worked)"
            else:
                status_reason = f"Present - Partial day ({total_hours:.1f} hours worked)"
        else:
            # Safety case - should not happen with new logic
            status_reason = "Present (attendance logs found)"
    
    # Update or create daily attendance record
    daily_record = DailyAttendance.query.filter_by(
        user_id=user_id,
        date=attendance_date
    ).first()
    
    if not daily_record:
        daily_record = DailyAttendance(
            user_id=user_id,
            date=attendance_date
        )
        db.session.add(daily_record)
    
    daily_record.first_check_in = first_check_in
    daily_record.last_check_out = last_check_out
    logging.debug(f"[ATTENDANCE_DEBUG] After daily_record assignment: daily_record.first_check_in={daily_record.first_check_in}, daily_record.last_check_out={daily_record.last_check_out}")
    
    daily_record.total_working_hours = total_working_minutes / 60
    daily_record.total_breaks = 0  # Not calculating breaks in new logic
    daily_record.entry_count = len(daily_logs)  # Total number of logs
    daily_record.status = status
    daily_record.status_reason = status_reason
    
    # Set incomplete day flag based on business rules:
    # Single log entry (any date) = incomplete, Multiple logs = complete
    daily_record.is_incomplete_day = is_incomplete_day
    
    # Store leave and permission information
    if leave_request:
        daily_record.leave_request_id = leave_request.id
        daily_record.leave_type_id = leave_request.leave_type_id
        if leave_request.leave_type:
            daily_record.leave_type_name = leave_request.leave_type.name
    
    if permission_request:
        daily_record.permission_request_id = permission_request.id
    
    if paid_holiday:
        daily_record.paid_holiday_id = paid_holiday.id
        daily_record.is_paid_holiday = True
        daily_record.holiday_name = paid_holiday.description
    
    return daily_record

def process_permission_requests_for_date(attendance_date):
    """Process permission requests for a given date and create daily attendance records"""
    from models import PermissionRequest, User
    
    # Get all approved permission requests for this date
    permission_requests = PermissionRequest.query.filter(
        PermissionRequest.status == 'approved',
        func.date(PermissionRequest.start_time) == attendance_date
    ).all()
    
    for permission_request in permission_requests:
        # Check if there's already a daily attendance record
        daily_record = DailyAttendance.query.filter_by(
            user_id=permission_request.user_id,
            date=attendance_date
        ).first()
        
        if not daily_record:
            # Create new daily attendance record for permission
            daily_record = DailyAttendance(
                user_id=permission_request.user_id,
                date=attendance_date,
                status='permission',
                status_reason=f"Approved Permission: {permission_request.reason[:50]}...",
                permission_request_id=permission_request.id
            )
            db.session.add(daily_record)
        else:
            # Update existing record to include permission info
            daily_record.status = 'permission'
            daily_record.status_reason = f"Approved Permission: {permission_request.reason[:50]}..."
            daily_record.permission_request_id = permission_request.id
    
    try:
        db.session.commit()
        logging.info(f"Processed {len(permission_requests)} permission requests for {attendance_date}")
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing permission requests for {attendance_date}: {str(e)}")

def process_paid_holidays_for_all_employees(attendance_date):
    """Process paid holidays for all active employees on a given date"""
    from models import PaidHoliday, User
    
    # Check if this date is a paid holiday
    paid_holiday = PaidHoliday.query.filter(
        or_(
            # Single day holiday
            and_(PaidHoliday.holiday_type == 'day',
                 PaidHoliday.start_date == attendance_date),
            # Range holiday that includes this date
            and_(PaidHoliday.holiday_type == 'range',
                 PaidHoliday.start_date <= attendance_date,
                 PaidHoliday.end_date >= attendance_date)
        )
    ).first()
    
    if not paid_holiday:
        return
    
    # Get all active employees
    active_employees = User.query.filter_by(status='active').all()
    
    for employee in active_employees:
        # Skip if employee joined after this date
        if employee.joining_date and attendance_date < employee.joining_date:
            continue
            
        # Check if there's already a daily attendance record
        daily_record = DailyAttendance.query.filter_by(
            user_id=employee.id,
            date=attendance_date
        ).first()
        
        if not daily_record:
            # Create new daily attendance record for paid holiday
            daily_record = DailyAttendance(
                user_id=employee.id,
                date=attendance_date,
                status='paid_holiday',
                status_reason=f"Paid Leave - {paid_holiday.description}",
                paid_holiday_id=paid_holiday.id,
                is_paid_holiday=True,
                holiday_name=paid_holiday.description
            )
            db.session.add(daily_record)
        else:
            # Update existing record to paid holiday status
            daily_record.status = 'paid_holiday'
            daily_record.status_reason = f"Paid Leave - {paid_holiday.description}"
            daily_record.paid_holiday_id = paid_holiday.id
            daily_record.is_paid_holiday = True
            daily_record.holiday_name = paid_holiday.description
    
    try:
        db.session.commit()
        logging.info(f"Processed paid holiday '{paid_holiday.description}' for all employees on {attendance_date}")
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing paid holiday for all employees: {str(e)}")

def cleanup_orphaned_attendance_records():
    """Clean up attendance records that reference deleted leave/permission requests"""
    from models import LeaveRequest, PermissionRequest, DailyAttendance
    from datetime import datetime, timedelta
    
    # Find attendance records with 'leave' status that don't have corresponding approved leave requests
    orphaned_leave_records = db.session.query(DailyAttendance).filter(
        DailyAttendance.status == 'leave'
    ).all()
    
    for record in orphaned_leave_records:
        # Check if there's still an approved leave request for this user and date
        leave_request = LeaveRequest.query.filter(
            LeaveRequest.user_id == record.user_id,
            LeaveRequest.start_date <= record.date,
            LeaveRequest.end_date >= record.date,
            LeaveRequest.status == 'approved'
        ).first()
        
        if not leave_request:
            # No approved leave request found, reset the record
            if not record.first_check_in and not record.last_check_out:
                record.status = 'absent'
                record.status_reason = None
            else:
                # Reprocess the day with actual attendance data
                process_daily_attendance(record.user_id, record.date)
    
    # Find attendance records with 'permission' status that don't have corresponding approved permission requests
    orphaned_permission_records = db.session.query(DailyAttendance).filter(
        DailyAttendance.status == 'permission'
    ).all()
    
    for record in orphaned_permission_records:
        # Check if there's still an approved permission request for this user and date
        permission_request = PermissionRequest.query.filter(
            PermissionRequest.user_id == record.user_id,
            func.date(PermissionRequest.start_time) == record.date,
            PermissionRequest.status == 'approved'
        ).first()
        
        if not permission_request:
            # No approved permission request found, reset the record
            if not record.first_check_in and not record.last_check_out:
                record.status = 'absent'
                record.status_reason = None
            else:
                # Reprocess the day with actual attendance data
                process_daily_attendance(record.user_id, record.date)
    
    try:
        db.session.commit()
        logging.info("Cleaned up orphaned attendance records")
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error cleaning up orphaned attendance records: {str(e)}")

def cleanup_duplicate_attendance_records():
    """Clean up duplicate attendance records for the same user and timestamp"""
    try:
        from sqlalchemy import func
        
        # Find duplicate records (same user_id and timestamp)
        duplicates = db.session.query(
            AttendanceLog.user_id,
            AttendanceLog.timestamp,
            func.count(AttendanceLog.id).label('count')
        ).group_by(
            AttendanceLog.user_id,
            AttendanceLog.timestamp
        ).having(func.count(AttendanceLog.id) > 1).all()
        
        if duplicates:
            logging.info(f'Found {len(duplicates)} sets of duplicate attendance records')
            
            total_removed = 0
            for user_id, timestamp, count in duplicates:
                # Get all records for this user and timestamp
                records = AttendanceLog.query.filter_by(
                    user_id=user_id,
                    timestamp=timestamp
                ).order_by(AttendanceLog.id).all()
                
                # Keep the first record, remove the rest
                for record in records[1:]:
                    db.session.delete(record)
                    total_removed += 1
            
            db.session.commit()
            logging.info(f'Cleaned up {total_removed} duplicate attendance records')
            return total_removed
        else:
            logging.info('No duplicate attendance records found')
            return 0
            
    except Exception as e:
        logging.error(f'Error cleaning up duplicate attendance records: {str(e)}')
        db.session.rollback()
        return 0

def get_active_device():
    """Get the active device settings or create default if none exists"""
    device = DeviceSettings.query.filter_by(is_active=True).first()
    
    if not device:
        # Create default device settings
        device = DeviceSettings(
            device_ip='192.168.11.2',
            device_port=4370,
            device_name='Default Device',
            is_active=True
        )
        db.session.add(device)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error creating default device settings: {str(e)}')
    
    return device

def test_device_connection():
    """Test connection to the fingerprint device with detailed diagnostics"""
    device = get_active_device()
    device_ip = device.device_ip
    device_port = device.device_port
    
    diagnostics = {
        'ping': False,
        'socket': False,
        'zk': False,
        'details': []
    }
    
    try:
        # 1. Ping Test
        logging.info(f'Testing ping to device {device_ip}...')
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        ping_cmd = ['ping', param, '1', device_ip]
        try:
            subprocess.check_output(ping_cmd, stderr=subprocess.STDOUT)
            diagnostics['ping'] = True
            diagnostics['details'].append('Ping successful')
        except subprocess.CalledProcessError as e:
            diagnostics['details'].append(f'Ping failed: {e.output.decode() if e.output else str(e)}')
            logging.error(f'Ping failed: {str(e)}')
        
        # 2. Socket Test
        logging.info('Testing socket connection...')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            result = sock.connect_ex((device_ip, device_port))
            if result == 0:
                diagnostics['socket'] = True
                diagnostics['details'].append('Socket connection successful')
            else:
                diagnostics['details'].append(f'Socket connection failed with error code: {result}')
        except Exception as e:
            diagnostics['details'].append(f'Socket error: {str(e)}')
            logging.error(f'Socket error: {str(e)}')
        finally:
            sock.close()
        
        # 3. ZK Connection Test
        logging.info(f'Attempting ZK connection to {device_ip}:{device_port}...')
        logging.info('Testing ZK connection...')
        zk = ZK(device_ip, port=device_port, timeout=30)
        conn = None
        
        try:
            conn = zk.connect()
            if conn:
                diagnostics['zk'] = True
                diagnostics['details'].append('ZK connection successful')
                
                # Get device info
                try:
                    info = {
                        'firmware': conn.get_firmware_version(),
                        'serial': conn.get_serialnumber(),
                        'platform': conn.get_platform(),
                        'name': conn.get_device_name(),
                        'users': len(conn.get_users() or [])
                    }
                    diagnostics['details'].append(f'Device info: {json.dumps(info)}')
                except Exception as e:
                    diagnostics['details'].append(f'Error getting device info: {str(e)}')
            else:
                diagnostics['details'].append('ZK connection failed')
                logging.error(f'ZK connection failed for {device_ip}:{device_port}')
        except Exception as e:
            diagnostics['details'].append(f'ZK error: {str(e)}')
            logging.error(f'ZK connection error for {device_ip}:{device_port}: {str(e)}')
        finally:
            if conn:
                conn.disconnect()
        
        return diagnostics['zk'], diagnostics
        
    except Exception as e:
        error_msg = f'Device connection test failed: {str(e)}'
        diagnostics['details'].append(error_msg)
        logging.error(error_msg)
        return False, diagnostics

def log_fingerprint_failure(error_type, error_message, device_ip, employee_id=None, raw_data=None):
    """Log a fingerprint failure event"""
    from flask import current_app
    try:
        with current_app.app_context():
            failure = FingerPrintFailure(
                error_type=error_type,
                error_message=error_message,
                device_ip=device_ip,
                employee_id=employee_id,
                raw_device_data=json.dumps(raw_data) if raw_data else None
            )
            db.session.add(failure)
            db.session.commit()
            
            # Admin notification removed - will be replaced with SMTP email notifications
            
            return failure
    except Exception as e:
        logging.error(f"Failed to log fingerprint failure: {str(e)}")
        with current_app.app_context():
            db.session.rollback()
        return None

def sync_attendance_from_device(device):
    """Sync attendance data from a specific device"""
    conn = None
    try:
        logging.info(f'Syncing data from device {device.get_display_name()} ({device.device_ip}:{device.device_port})')
        
        # Connect to device with increased timeout protection (30 seconds for large datasets)
        zk = ZK(device.device_ip, port=device.device_port, timeout=30)
        try:
            conn = zk.connect()
        except Exception as conn_error:
            error_msg = f'Connection error to device {device.get_display_name()}: {str(conn_error)}'
            logging.error(error_msg)
            return {
                'status': 'error',
                'message': error_msg,
                'records_added': 0,
                'records_updated': 0
            }
        
        if not conn:
            error_msg = f'Could not connect to device {device.get_display_name()}'
            logging.error(error_msg)
            return {
                'status': 'error',
                'message': error_msg,
                'records_added': 0,
                'records_updated': 0
            }
        
        # Get attendance records from device with error handling and timeout protection
        try:
            logging.info(f'Fetching attendance records from {device.get_display_name()}...')
            attendance_records = conn.get_attendance()
            total_records = len(attendance_records) if attendance_records else 0
            logging.info(f'Retrieved {total_records} records from {device.get_display_name()}')
            
            # Log date range to verify we're getting all available data
            if attendance_records and total_records > 0:
                timestamps = [r.timestamp for r in attendance_records]
                oldest = min(timestamps)
                newest = max(timestamps)
                days_span = (newest - oldest).days
                logging.info(f'Date range in device records: {oldest.strftime("%Y-%m-%d %H:%M:%S")} to {newest.strftime("%Y-%m-%d %H:%M:%S")} ({days_span} days)')
        except Exception as get_error:
            error_msg = f'Error retrieving attendance from device {device.get_display_name()}: {str(get_error)}'
            logging.error(error_msg, exc_info=True)
            return {
                'status': 'error',
                'message': error_msg,
                'records_added': 0,
                'records_updated': 0
            }
        if not attendance_records:
            return {
                'status': 'success',
                'message': f'No new records found on {device.get_display_name()}',
                'records_added': 0
            }
        
        # Process records in batches for better performance
        records_added = 0
        records_updated = 0
        unmatched_records = 0
        batch_size = 500  # Increased batch size for better performance
        
        total_records = len(attendance_records) if attendance_records else 0
        logging.info(f'Processing {total_records} records from device {device.get_display_name()} in batches of {batch_size}')
        
        # Log progress periodically to help debug long-running syncs
        progress_interval = max(1000, total_records // 10)  # Log every 10% or every 1000 records, whichever is larger
        
        # Pre-cache user lookups by fingerprint number for better performance
        user_cache = {}
        fingerprint_numbers = set(str(r.user_id) for r in attendance_records)
        if fingerprint_numbers:
            cached_users = safe_db_query(
                lambda: User.query.filter(User.fingerprint_number.in_(fingerprint_numbers)).all(),
                default=[]
            )
            user_cache = {str(u.fingerprint_number): u for u in cached_users if u.fingerprint_number}
        
        # Pre-fetch existing records in batches to reduce queries
        new_records = []
        
        for idx, record in enumerate(attendance_records):
            # Find user from cache
            user = user_cache.get(str(record.user_id))
            
            if not user:
                # Try to find user (fallback)
                user = find_user_for_device_record(device, record.user_id)
                if user:
                    user_cache[str(record.user_id)] = user
                else:
                    unmatched_records += 1
                    if unmatched_records <= 5:
                        logging.warning(f'No user found for fingerprint number {record.user_id} on device {device.get_display_name()}')
                    continue
            
            # Collect records for batch processing
            new_records.append({
                'user_id': user.id,
                'timestamp': record.timestamp,
                'scan_type': determine_attendance_type(record.timestamp),
                'device_ip': device.device_ip,
                'device_id': device.id
            })
            
            # Commit in batches
            if len(new_records) >= batch_size:
                # Batch check for existing records
                timestamps = [r['timestamp'] for r in new_records]
                user_ids = list(set(r['user_id'] for r in new_records))
                
                existing_records = safe_db_query(
                    lambda: AttendanceLog.query.filter(
                        AttendanceLog.user_id.in_(user_ids),
                        AttendanceLog.timestamp.in_(timestamps)
                    ).all(),
                    default=[]
                )
                
                existing_map = {(r.user_id, r.timestamp): r for r in existing_records}
                
                # Process batch
                for rec_data in new_records:
                    key = (rec_data['user_id'], rec_data['timestamp'])
                    existing = existing_map.get(key)
                    
                    if existing:
                        if existing.device_id != device.id:
                            existing.device_ip = rec_data['device_ip']
                            existing.device_id = rec_data['device_id']
                            records_updated += 1
                        else:
                            existing.scan_type = rec_data['scan_type']
                            records_updated += 1
                    else:
                        attendance_log = AttendanceLog(**rec_data)
                        db.session.add(attendance_log)
                        records_added += 1
                
                # Commit batch
                try:
                    db.session.commit()
                    # Log progress periodically
                    if (idx + 1) % progress_interval == 0 or (idx + 1) == total_records:
                        logging.info(f'Progress: {idx + 1}/{total_records} records processed ({records_added} added, {records_updated} updated)')
                except Exception as commit_error:
                    db.session.rollback()
                    logging.error(f'Error committing batch: {str(commit_error)}')
                    # Continue with next batch
                
                new_records = []
        
        # Process remaining records
        if new_records:
            timestamps = [r['timestamp'] for r in new_records]
            user_ids = list(set(r['user_id'] for r in new_records))
            
            existing_records = safe_db_query(
                lambda: AttendanceLog.query.filter(
                    AttendanceLog.user_id.in_(user_ids),
                    AttendanceLog.timestamp.in_(timestamps)
                ).all(),
                default=[]
            )
            
            existing_map = {(r.user_id, r.timestamp): r for r in existing_records}
            
            for rec_data in new_records:
                key = (rec_data['user_id'], rec_data['timestamp'])
                existing = existing_map.get(key)
                
                if existing:
                    if existing.device_id != device.id:
                        existing.device_ip = rec_data['device_ip']
                        existing.device_id = rec_data['device_id']
                        records_updated += 1
                    else:
                        existing.scan_type = rec_data['scan_type']
                        records_updated += 1
                else:
                    attendance_log = AttendanceLog(**rec_data)
                    db.session.add(attendance_log)
                    records_added += 1
        
        # Commit remaining changes
        if new_records:
            try:
                db.session.commit()
                logging.info(f'Committed final batch: {total_records} records processed')
            except Exception as commit_error:
                db.session.rollback()
                error_msg = f'Error committing final batch: {str(commit_error)}'
                logging.error(error_msg)
                raise Exception(error_msg)
        
        # Calculate summary statistics
        total_fetched = total_records
        total_processed = records_added + records_updated
        total_skipped = unmatched_records
        
        logging.info(f'Sync completed for {device.get_display_name()}:')
        logging.info(f'  Total fetched from device: {total_fetched}')
        logging.info(f'  Records added: {records_added}')
        logging.info(f'  Records updated: {records_updated}')
        logging.info(f'  Total processed: {total_processed}')
        logging.info(f'  Unmatched (skipped): {unmatched_records}')
        
        if total_fetched > 0:
            processing_rate = (total_processed / total_fetched) * 100
            logging.info(f'  Processing rate: {processing_rate:.1f}% ({total_processed}/{total_fetched})')
        
        return {
            'status': 'success',
            'message': f'Synced {records_added} new records from {device.get_display_name()} (fetched {total_fetched}, processed {total_processed}, unmatched {unmatched_records})',
            'records_added': records_added,
            'records_updated': records_updated,
            'unmatched': unmatched_records,
            'total_fetched': total_fetched,
            'total_processed': total_processed
        }
        
    except Exception as e:
        logging.error(f'Error syncing device {device.get_display_name()}: {str(e)}')
        db.session.rollback()
        return {
            'status': 'error',
            'message': f'Error syncing {device.get_display_name()}: {str(e)}',
            'records_added': 0
        }
    finally:
        # Always disconnect from device, even if there was an error
        if conn:
            try:
                conn.disconnect()
                logging.info(f'Disconnected from device {device.get_display_name()}')
            except Exception as disconnect_error:
                logging.warning(f'Error disconnecting from device {device.get_display_name()}: {str(disconnect_error)}')

def find_user_for_device_record(device, device_user_id):
    """Find system user for a device record using fingerprint number"""
    try:
        # Direct match by fingerprint number
        user = safe_db_query(
            lambda: User.query.filter_by(fingerprint_number=str(device_user_id)).first(),
            default=None
        )
        if user:
            return user
        
        # Check if there's a processed device user with this fingerprint ID
        device_user = safe_db_query(
            lambda: DeviceUser.query.filter_by(
            device_user_id=str(device_user_id),
            is_processed=True
            ).first(),
            default=None
        )
        
        if device_user and device_user.system_user_id:
            return safe_db_query(
                lambda: User.query.get(device_user.system_user_id),
                default=None
            )
        
        # If no match, automatically create a system user for this fingerprint
        try:
            # Create a basic device user data structure
            device_user_data = {
                'name': f'User{device_user_id}',
                'user_id': device_user_id
            }
            
            # Auto-create system user
            system_user = create_system_user_from_device_user(device_user_data, str(device_user_id))
            if system_user:
                logging.info(f'Auto-created system user for unmatched attendance record: {system_user.first_name} (fingerprint: {device_user_id})')
                return system_user
            
        except Exception as e:
            logging.error(f'Error auto-creating system user for unmatched record {device_user_id}: {str(e)}')
        
        return None
        
    except Exception as e:
        logging.error(f'Error finding user for device record: {str(e)}')
        return None


def sync_attendance_task(full_sync=False):
    """Sync attendance data from all active fingerprint devices"""
    from flask import current_app
    from connection_manager import safe_sync_operation, managed_db_session
    import uuid
    
    # Generate unique operation ID
    operation_id = str(uuid.uuid4())
    
    @safe_sync_operation(operation_id)
    def _sync_attendance():
        try:
            # Clean up orphaned paid holiday records first
            cleanup_orphaned_paid_holiday_records()
            
            # Get all active devices
            active_devices = safe_db_query(
                lambda: DeviceSettings.query.filter_by(is_active=True).all(),
                default=[]
            )
            if not active_devices:
                error_msg = 'No active devices found'
                logging.error(error_msg)
                return {
                    'status': 'error',
                    'message': error_msg
                }
            
            # Sync from all active devices
            total_records_added = 0
            total_records_updated = 0
            total_unmatched = 0
            device_results = []
            
            for device in active_devices:
                logging.info(f'Syncing from device: {device.get_display_name()}')
                result = sync_attendance_from_device(device)
                device_results.append({
                    'device_name': device.get_display_name(),
                    'result': result
                })
                
                if result['status'] == 'success':
                    total_records_added += result.get('records_added', 0)
                    total_records_updated += result.get('records_updated', 0)
                    total_unmatched += result.get('unmatched', 0)
            
            device_names = [device.get_display_name() for device in active_devices]
            return {
                'status': 'success',
                'message': f'Synced from {len(active_devices)} devices ({", ".join(device_names)}): {total_records_added} added, {total_records_updated} updated, {total_unmatched} unmatched',
                'records_added': total_records_added,
                'records_updated': total_records_updated,
                'unmatched': total_unmatched,
                'device_results': device_results,
                'devices_synced': device_names
            }
        
        except Exception as e:
            error_msg = f'Error during sync: {str(e)}'
            logging.error(error_msg)
            return {
                'status': 'error',
                'message': error_msg
            }
    
    return _sync_attendance()
            

@attendance_bp.route('/last-fingerprint-reading')
@login_required
@role_required(['admin', 'product_owner'])
def last_fingerprint_reading():
    last_reading = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc()).first()
    if last_reading:
        message = f"Last Fingerprint Reading: {last_reading.timestamp} for User ID: {last_reading.user_id} (Scan Type: {last_reading.scan_type})"
    else:
        message = "No fingerprint readings found."
    flash(message, 'info')
    return redirect(url_for('dashboard.index'))

@attendance_bp.route('/sync-all-device-users', methods=['POST'])
@login_required
@role_required(['product_owner'])  # Only Product Owner can sync users
def sync_all_device_users():
    """Sync users from all active devices to system users"""
    try:
        # Check if there are any active devices
        active_devices = DeviceSettings.query.filter_by(is_active=True).all()
        if not active_devices:
            return jsonify({
                'status': 'error',
                'message': 'No active devices found. Please add and activate devices in Device Settings.'
            }), 400
        
        # Log the devices that will be synced
        device_names = [device.get_display_name() for device in active_devices]
        logging.info(f'Device users sync requested for {len(active_devices)} active devices: {", ".join(device_names)}')
        
        total_users_added = 0
        total_users_updated = 0
        device_results = []
        
        for device in active_devices:
            try:
                # Sync users from this device
                success = sync_device_users_to_table(device)
                
                if success:
                    # Count how many users were added/updated for this device
                    device_users = DeviceUser.query.filter_by(device_id=device.id).all()
                    processed_users = [du for du in device_users if du.is_processed]
                    
                    device_results.append({
                        'device_name': device.get_display_name(),
                        'success': True,
                        'total_users': len(device_users),
                        'processed_users': len(processed_users)
                    })
                    
                    # Count new system users created
                    new_users = User.query.filter(
                        User.fingerprint_number.in_([du.device_user_id for du in device_users if du.is_processed])
                    ).count()
                    
                    total_users_added += new_users
                    total_users_updated += len(processed_users) - new_users
                else:
                    device_results.append({
                        'device_name': device.get_display_name(),
                        'success': False,
                        'error': 'Failed to connect to device'
                    })
                    
            except Exception as e:
                logging.error(f'Error syncing users from device {device.get_display_name()}: {str(e)}')
                device_results.append({
                    'device_name': device.get_display_name(),
                    'success': False,
                    'error': str(e)
                })
        
        # Count successful device syncs
        successful_syncs = len([r for r in device_results if r['success']])
        
        return jsonify({
            'status': 'success',
            'message': f'Synced users from {successful_syncs}/{len(active_devices)} devices. {total_users_added} new users added, {total_users_updated} users updated.',
            'devices_synced': successful_syncs,
            'total_devices': len(active_devices),
            'users_added': total_users_added,
            'users_updated': total_users_updated,
            'device_results': device_results
        })
        
    except Exception as e:
        logging.error(f'Error syncing device users: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'Error syncing device users: {str(e)}'
        }), 500

@attendance_bp.route('/clear-sync-lock', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def clear_sync_lock():
    """Clear stuck sync operations (Admin/Product Owner only)"""
    try:
        from connection_manager import clear_all_sync_operations
        cleared_count = clear_all_sync_operations()
        
        logging.warning(f"User {current_user.get_full_name()} ({current_user.role}) manually cleared {cleared_count} sync operations")
        
        return jsonify({
            'status': 'success',
            'message': f'Cleared {cleared_count} stuck sync operations. You can now try syncing again.',
            'cleared_count': cleared_count
        })
    except Exception as e:
        logging.error(f"Error clearing sync lock: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error clearing sync operations: {str(e)}'
        }), 500

@attendance_bp.route('/manual-sync', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def manual_sync():
    """Manually trigger attendance synchronization"""
    if not current_app.config.get('IS_ADMIN_INSTANCE', False):
        return jsonify({'status': 'error', 'message': 'This feature is only available on the admin portal.'}), 403

    # Check if sync is already running using connection manager
    from connection_manager import is_sync_running, clear_all_sync_operations
    if is_sync_running():
        # For Admin and Product Owner, allow force clearing stuck syncs after a timeout
        if current_user.role in ['admin', 'product_owner']:
            import time
            # Check if we should clear stuck operations (after 5 minutes)
            sync_timeout = 300  # 5 minutes
            try:
                # Clear stuck operations for admin users
                cleared_count = clear_all_sync_operations()
                if cleared_count > 0:
                    logging.warning(f"Admin {current_user.get_full_name()} cleared {cleared_count} stuck sync operations")
                    # Continue with sync after clearing
                else:
                    return jsonify({'status': 'info', 'message': 'Another sync operation is already running. Please wait.'}), 200
            except Exception as e:
                logging.error(f"Error clearing sync operations: {str(e)}")
                return jsonify({'status': 'info', 'message': 'Another sync operation is already running. Please wait.'}), 200
        else:
            return jsonify({'status': 'info', 'message': 'Another sync operation is already running. Please wait.'}), 200

    # Check scheduler status - removed job state check as it's not reliable
    # The connection manager already handles sync conflicts

    # Check if there are any active devices
    active_devices = safe_db_query(
        lambda: DeviceSettings.query.filter_by(is_active=True).all(),
        default=[]
    )
    if not active_devices:
        return jsonify({
            'status': 'error',
            'message': 'No active devices found. Please add and activate devices in Device Settings.'
        }), 400
    
    # Log the devices that will be synced
    device_names = [device.get_display_name() for device in active_devices]
    logging.info(f'Manual sync requested for {len(active_devices)} active devices: {", ".join(device_names)}')

    # Run sync synchronously but with proper error handling
    try:
        # Store user role for use in cleanup
        user_role = current_user.role
        
        # Run cleanup first for admin users
        if user_role in ['admin', 'director']:
            try:
                cleanup_orphaned_attendance_records()
                cleanup_duplicate_attendance_records()
                logging.info('Cleanup completed during manual sync')
            except Exception as e:
                logging.error(f'Error during cleanup in manual sync: {str(e)}')
                # Continue with sync even if cleanup fails
        
        # Run sync with timeout protection
        logging.info(f'Starting manual sync for {len(active_devices)} devices')
        
        sync_results = None
        try:
            # Ensure we have a clean session before sync
            db.session.rollback()
            
            # Call sync with explicit error handling and timeout protection
            try:
                # Use a signal or timeout wrapper if needed (for very long operations)
                # For now, we rely on proper error handling and logging
                sync_results = sync_attendance_task(full_sync=True)
                
                # Log completion
                if sync_results:
                    logging.info(f'Manual sync completed: status={sync_results.get("status")}, records_added={sync_results.get("records_added", 0)}')
                else:
                    logging.warning('Manual sync returned None')
                
                # Ensure session is clean after sync
                try:
                    db.session.commit()
                except Exception as commit_err:
                    db.session.rollback()
                    logging.warning(f'Session commit warning after sync: {commit_err}')
            except KeyboardInterrupt:
                # Handle user interruption
                logging.warning('Sync interrupted by user')
                db.session.rollback()
                sync_results = {
                    'status': 'error',
                    'message': 'Sync was interrupted. Please try again.'
                }
            except Exception as sync_inner_error:
                logging.error(f'Error in sync_attendance_task: {str(sync_inner_error)}', exc_info=True)
                db.session.rollback()
                # Create a proper error response
                error_msg = str(sync_inner_error)[:200]
                sync_results = {
                    'status': 'error',
                    'message': f'Sync failed: {error_msg}'
                }
        except Exception as sync_error:
            logging.error(f'Error calling sync_attendance_task: {str(sync_error)}', exc_info=True)
            # Rollback any failed transaction
            try:
                db.session.rollback()
            except Exception:
                pass
            # Return error response - ensure it's a valid JSON response
            try:
                return jsonify({
                    'status': 'error',
                    'message': f'Sync task failed: {str(sync_error)[:200]}'
                }), 500
            except Exception as json_error:
                logging.error(f'Error creating JSON response: {str(json_error)}')
                # Fallback: return simple text response
                from flask import Response
                return Response(
                    f'{{"status":"error","message":"Sync task failed: {str(sync_error)[:200]}"}}',
                    status=500,
                    mimetype='application/json'
                )
        
        # Validate sync_results - ensure we always have a response
        if not sync_results:
            logging.error('sync_attendance_task returned None - creating fallback response')
            sync_results = {
                'status': 'error',
                'message': 'Sync failed: No response from sync task. The sync may have timed out or encountered an error. Check server logs for details.'
            }
        
        if not isinstance(sync_results, dict):
            logging.error(f'sync_attendance_task returned invalid type: {type(sync_results)}')
            return jsonify({
                'status': 'error',
                'message': f'Sync failed: Invalid response from sync task. Check server logs for details.'
            }), 500
        
        if 'status' not in sync_results:
            logging.error(f'sync_attendance_task returned invalid response: {sync_results}')
            return jsonify({
                'status': 'error',
                'message': 'Sync failed: Invalid response format from sync task. Check server logs for details.'
            }), 500
        
        # Return results based on sync status
        if sync_results['status'] == 'success':
            return jsonify({
                'status': 'success',
                'message': sync_results.get('message', 'Sync completed successfully'),
                'records_added': sync_results.get('records_added', 0),
                'records_updated': sync_results.get('records_updated', 0),
                'devices_count': len(active_devices)
            })
        elif sync_results['status'] == 'skipped':
            return jsonify({
                'status': 'info',
                'message': sync_results.get('message', 'Sync was skipped')
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': sync_results.get('message', 'Sync failed with unknown error')
            }), 500
            
    except Exception as e:
        logging.error(f'Error in manual sync: {str(e)}', exc_info=True)
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        # Always return a valid JSON response, even on unexpected errors
        try:
            return jsonify({
                'status': 'error',
                'message': f'Sync failed: {str(e)[:500]}'  # Limit message length
            }), 500
        except Exception as json_error:
            # Last resort: return a simple text response
            logging.error(f'Failed to create JSON response: {str(json_error)}')
            from flask import Response
            return Response(
                '{"status":"error","message":"Sync failed due to an internal error. Check server logs for details."}',
                status=500,
                mimetype='application/json'
            )

@attendance_bp.route('/test-sync', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def test_sync():
    """Test sync functionality - simplified version for debugging"""
    try:
        # Basic checks
        active_devices = DeviceSettings.query.filter_by(is_active=True).all()
        if not active_devices:
            return jsonify({
                'status': 'error',
                'message': 'No active devices found. Please add and activate devices in Device Settings.'
            }), 400
        
        device_names = [device.get_display_name() for device in active_devices]
        
        return jsonify({
            'status': 'success',
            'message': f'Test successful. Found {len(active_devices)} active devices: {", ".join(device_names)}',
            'devices_count': len(active_devices),
            'devices': device_names
        })
        
    except Exception as e:
        logging.error(f'Error in test sync: {str(e)}', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Test failed: {str(e)}'
        }), 500

@attendance_bp.route('/clear-sync', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def clear_sync():
    """Clear stuck sync operations"""
    if not current_app.config.get('IS_ADMIN_INSTANCE', False):
        return jsonify({'status': 'error', 'message': 'This feature is only available on the admin portal.'}), 403

    try:
        from connection_manager import clear_all_sync_operations
        cleared_count = clear_all_sync_operations()
        return jsonify({
            'status': 'success',
            'message': f'Cleared {cleared_count} stuck sync operations',
            'cleared_count': cleared_count
        })
    except Exception as e:
        logging.error(f'Error clearing sync operations: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'Failed to clear sync operations: {str(e)}'
        }), 500

@attendance_bp.route('/cleanup-orphaned', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def cleanup_orphaned():
    """Clean up orphaned attendance records"""
    try:
        cleanup_orphaned_attendance_records()
        return jsonify({
            'status': 'success',
            'message': 'Orphaned attendance records cleaned up successfully!'
        })
    except Exception as e:
        logging.error(f'Error cleaning up orphaned records: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'Error cleaning up orphaned records: {str(e)}'
        }), 500

@attendance_bp.route('/cleanup-duplicates', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def cleanup_duplicates():
    """Clean up duplicate attendance records"""
    try:
        removed_count = cleanup_duplicate_attendance_records()
        return jsonify({
            'status': 'success',
            'message': f'Cleaned up {removed_count} duplicate records successfully'
        })
    except Exception as e:
        logging.error(f'Error in cleanup_duplicates: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'Cleanup failed: {str(e)}'
        }), 500

@attendance_bp.route('/')
@login_required
def index():
    """Show the attendance page with today's records and historical data"""
    # Check for cache-busting parameter
    force_refresh = request.args.get('refresh', type=bool, default=False)
    
    # Show refresh message if page was refreshed
    if force_refresh:
        flash('Page refreshed to show latest attendance data.', 'info')
    
    # Clean up orphaned paid holiday records on every page load
    cleanup_orphaned_paid_holiday_records()
    
    # For employees, show their own detailed logs instead of redirecting
    if current_user.role == 'employee':
        # Set employee_id to current user's ID to filter logs for them only
        employee_id = current_user.id
    else:
        employee_id = request.args.get('employee_id', type=int)
    # Auto-sync data from device when page loads (non-blocking) - only if no sync is running
    from connection_manager import is_sync_running
    
    if not is_sync_running():
        try:
            # Run sync and cleanup in a separate thread to avoid blocking the page load
            import threading
            from flask import current_app
            
            def sync_and_cleanup_task():
                try:
                    with current_app.app_context():
                        # Run cleanup first
                        if current_user.role in ['admin', 'director']:
                            try:
                                cleanup_orphaned_attendance_records()
                                logging.info('Cleanup completed on page load')
                            except Exception as e:
                                logging.error(f'Error during cleanup on page load: {str(e)}')
                        
                        # Then run sync
                        sync_attendance_task(full_sync=True)
                except Exception as e:
                    logging.error(f'Error auto-syncing data on page load: {str(e)}')
            
            sync_thread = threading.Thread(target=sync_and_cleanup_task, daemon=True)
            sync_thread.start()
        except Exception as e:
            logging.error(f'Error starting sync thread: {str(e)}')
    else:
        logging.info('Skipping sync on attendance page load - another sync is already running')
    
    # Check if user is admin or if employee is viewing their own data
    is_admin = current_user.is_authenticated and current_user.is_admin()
    is_employee_viewing_own_data = current_user.role == 'employee' and employee_id == current_user.id
    
    # Get today's date range
    today = datetime.now().date()
    start_datetime = datetime.combine(today, datetime.min.time())
    end_datetime = datetime.combine(today, datetime.max.time())
    
    try:
        # Get today's attendance logs
        today_logs = safe_db_query(
            lambda: AttendanceLog.query\
            .filter(AttendanceLog.timestamp.between(start_datetime, end_datetime))\
            .order_by(AttendanceLog.timestamp.desc())\
                .all(),
            default=[]
        )
        
        # Get users based on role
        if current_user.role in ['admin', 'product_owner', 'director']:
            # Admins, Product Owners, and directors can see all users
            all_active_users = safe_db_query(
                lambda: User.query.filter_by(status='active').filter(
                User.fingerprint_number != None,
                User.fingerprint_number != '',
                User.first_name != None,
                User.first_name != '',
                User.last_name != None,
                User.last_name != ''
                ).order_by(User.first_name.desc(), User.last_name.desc()).all(),
                default=[]
            )
        elif current_user.role == 'manager':
            # Managers can see all employees in their department
            if current_user.department_id:
                all_active_users = safe_db_query(
                    lambda: User.query.filter_by(status='active', department_id=current_user.department_id).filter(
                    User.fingerprint_number != None,
                    User.fingerprint_number != '',
                    User.first_name != None,
                    User.first_name != '',
                    User.last_name != None,
                    User.last_name != ''
                    ).order_by(User.first_name.desc(), User.last_name.desc()).all(),
                    default=[]
                )
            else:
                # If manager has no department assigned, they can only see themselves
                all_active_users = safe_db_query(
                    lambda: User.query.filter_by(id=current_user.id, status='active').filter(
                    User.fingerprint_number != None,
                    User.fingerprint_number != '',
                    User.first_name != None,
                    User.first_name != '',
                    User.last_name != None,
                    User.last_name != ''
                    ).order_by(User.first_name.desc(), User.last_name.desc()).all(),
                    default=[]
                )
        else:
            # Employees can only see their own attendance
            all_active_users = safe_db_query(
                lambda: User.query.filter_by(id=current_user.id, status='active').filter(
                User.fingerprint_number != None,
                User.fingerprint_number != '',
                User.first_name != None,
                User.first_name != '',
                User.last_name != None,
                User.last_name != ''
                ).order_by(User.first_name.desc(), User.last_name.desc()).all(),
                default=[]
            )

        # Process today's logs
        processed_logs = process_attendance_logs(today_logs)
        
        # Debug logging
        logging.info(f'Fetched {len(today_logs)} attendance logs for today')
        logging.info(f'Found {len(all_active_users)} active users with fingerprint numbers')
        logging.info(f'Processed logs for {len(processed_logs)} users')
    except Exception as e:
        logging.error(f'Error fetching attendance data: {str(e)}')
        # Set default values to prevent page from breaking
        today_logs = []
        all_active_users = []
        processed_logs = {}

    daily_attendance = {}
    today_weekday = today.weekday() # Monday is 0, Sunday is 6
    is_weekend = (today_weekday == 4 or today_weekday == 5) # Friday is 4, Saturday is 5

    # Create two separate dictionaries for present and absent users
    present_users = {}
    absent_users = {}

    for user in all_active_users:
        # If employee is viewing their own data, only process their records
        if is_employee_viewing_own_data and user.id != current_user.id:
            continue
            
        # Check if user has an approved leave for today
        leave_request = safe_db_query(
            lambda: LeaveRequest.query.filter(
                LeaveRequest.user_id == user.id,
                LeaveRequest.status == 'approved',
                LeaveRequest.start_date <= today,
                LeaveRequest.end_date >= today
            ).first(),
            default=None
        )
        is_on_leave = leave_request is not None
        
        # Check if user has an approved permission for today
        permission_request = safe_db_query(
            lambda: PermissionRequest.query.filter(
                PermissionRequest.user_id == user.id,
                PermissionRequest.status == 'approved',
                func.date(PermissionRequest.start_time) == today
            ).first(),
            default=None
        )
        has_permission = permission_request is not None
        
        # Check if user has a daily attendance record for today
        daily_record = safe_db_query(
            lambda: DailyAttendance.query.filter_by(
            user_id=user.id,
            date=today
            ).first(),
            default=None
        )
        
        if daily_record and daily_record.status in ['leave', 'permission', 'paid_holiday']:
            # User has a daily attendance record with leave, permission, or paid holiday status
            if daily_record.status == 'leave':
                status = 'leave'
                # Get the leave request details
                leave_request = safe_db_query(
                    lambda: LeaveRequest.query.filter(
                    LeaveRequest.user_id == user.id,
                    LeaveRequest.status == 'approved',
                    LeaveRequest.start_date <= today,
                    LeaveRequest.end_date >= today
                    ).first(),
                    default=None
                )
                absent_users[user.id] = {
                    'user': user,
                    'check_in': None,
                    'check_out': None,
                    'duration': None,
                    'status': status,
                    'leave_request': leave_request,
                    'leave_type_name': daily_record.leave_type_name,
                    'leave_type_id': daily_record.leave_type_id
                }
            elif daily_record.status == 'permission':
                # For permission requests, show attendance logs if they exist
                if user.id in processed_logs:
                    # User has attendance logs - show them with permission annotation
                    user_data = processed_logs[user.id]
                    user_data['status'] = 'present'  # Show as present with permission info
                    user_data['permission_request'] = PermissionRequest.query.filter(
                        PermissionRequest.user_id == user.id,
                        PermissionRequest.status == 'approved',
                        func.date(PermissionRequest.start_time) == today
                    ).first()
                    present_users[user.id] = user_data
                else:
                    # No attendance logs - show as permission only
                    status = 'permission'
                permission_request = PermissionRequest.query.filter(
                    PermissionRequest.user_id == user.id,
                    PermissionRequest.status == 'approved',
                    func.date(PermissionRequest.start_time) == today
                ).first()
                absent_users[user.id] = {
                    'user': user,
                    'check_in': None,
                    'check_out': None,
                    'duration': None,
                    'status': status,
                    'permission_request': permission_request
                    }
            elif daily_record.status == 'paid_holiday':
                # Check if the paid holiday still exists in the database
                from models import PaidHoliday
                paid_holiday_exists = PaidHoliday.query.filter_by(id=daily_record.paid_holiday_id).first() if daily_record.paid_holiday_id else None
                
                if paid_holiday_exists:
                    # Paid holiday still exists - show it
                    if user.id in processed_logs:
                        # User has attendance logs - show them with paid holiday annotation
                        user_data = processed_logs[user.id]
                        user_data['status'] = f"Present - {daily_record.holiday_name}"  # Show as present with paid holiday info
                        user_data['holiday_name'] = daily_record.holiday_name
                        user_data['paid_holiday_id'] = daily_record.paid_holiday_id
                        present_users[user.id] = user_data
                    else:
                        # No attendance logs - show as paid holiday only
                        status = daily_record.holiday_name  # Show the holiday name as status
                        absent_users[user.id] = {
                            'user': user,
                            'check_in': None,
                            'check_out': None,
                            'duration': None,
                            'status': status,
                            'holiday_name': daily_record.holiday_name,
                            'paid_holiday_id': daily_record.paid_holiday_id
                        }
                else:
                    # Paid holiday no longer exists - clean up the record and show normal attendance
                    logging.info(f"Cleaning up orphaned paid holiday record for user {user.id} on {today}")
                    db.session.delete(daily_record)
                    db.session.commit()
                    
                    # Re-evaluate attendance without the paid holiday record
                    if user.id in processed_logs:
                        # User has attendance logs - show as present
                        user_data = processed_logs[user.id]
                        user_data['status'] = 'present'
                        present_users[user.id] = user_data
                    else:
                        # No attendance logs - show as absent
                        absent_users[user.id] = {
                            'user': user,
                            'check_in': None,
                            'check_out': None,
                            'duration': None,
                            'status': 'Absent'
                }
        elif user.id in processed_logs:
            # User has attendance logs
            user_data = processed_logs[user.id]
            if is_on_leave:
                user_data['status'] = 'present'  # Show as present with leave info
                user_data['leave_request'] = leave_request
                # Add leave type information from daily record if available
                if daily_record and daily_record.leave_type_name:
                    user_data['leave_type_name'] = daily_record.leave_type_name
                    user_data['leave_type_id'] = daily_record.leave_type_id
            elif has_permission:
                user_data['status'] = 'present'  # Show as present with permission info
                user_data['permission_request'] = permission_request
            elif is_weekend and user_data['status'] == 'present':
                user_data['status'] = 'DayOff / Present'
            # Check if there's a paid holiday for today
            elif daily_record and daily_record.status == 'paid_holiday':
                user_data['status'] = 'present'  # Show as present with holiday info
                user_data['holiday_name'] = daily_record.holiday_name
                user_data['paid_holiday_id'] = daily_record.paid_holiday_id
            present_users[user.id] = user_data
        else:
            # User has no attendance logs for today
            if is_on_leave:
                status = 'leave'
                absent_users[user.id] = {
                    'user': user,
                    'check_in': None,
                    'check_out': None,
                    'duration': None,
                    'status': status,
                    'leave_request': leave_request,
                    'leave_type_name': daily_record.leave_type_name if daily_record else None,
                    'leave_type_id': daily_record.leave_type_id if daily_record else None
                }
            elif has_permission:
                status = 'permission'
                absent_users[user.id] = {
                    'user': user,
                    'check_in': None,
                    'check_out': None,
                    'duration': None,
                    'status': status,
                    'permission_request': permission_request
                }
            elif daily_record and daily_record.status == 'paid_holiday':
                status = 'paid_holiday'
                absent_users[user.id] = {
                    'user': user,
                    'check_in': None,
                    'check_out': None,
                    'duration': None,
                    'status': status,
                    'holiday_name': daily_record.holiday_name,
                    'paid_holiday_id': daily_record.paid_holiday_id
                }
            else:
                status = 'DayOff' if is_weekend else 'Absent'
                absent_users[user.id] = {
                    'user': user,
                    'check_in': None,
                    'check_out': None,
                    'duration': None,
                    'status': status
                }
    
    # Sort present users by check-in time in descending order (latest check-in first)
    sorted_present_users = {}
    if present_users:
        # Convert to list of tuples (user_id, data) for sorting
        present_items = list(present_users.items())
        # Sort by check-in time in descending order (latest first)
        # If check_in is None, put at the end of present users
        present_items.sort(key=lambda x: (x[1]['check_in'] is None, 
                                        -x[1]['check_in'].timestamp.timestamp() if x[1]['check_in'] else 0))
        # Convert back to dictionary
        sorted_present_users = {user_id: data for user_id, data in present_items}
    
    # Combine the dictionaries with sorted present users first, then absent users
    daily_attendance = {**sorted_present_users, **absent_users}
    
    # Handle historical data if date range is provided
    historical_attendance = {}
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Admin-only employee filter
    employee_id = request.args.get('employee_id')
    employee_data = None
    attendance_summary = None
    # Calculate attendance summary if historical data is available and employee_id is specified
    if historical_attendance and employee_id:
        total_days = len(all_dates)
        present_days = 0
        absent_days = 0
        leave_days = 0
        day_offs = 0
        extra_hours = timedelta(0)

        for date_key, records in historical_attendance.items():
            for record in records.values():
                if record['user'].id == employee_id:
                    if record['status'] == 'Present':
                        present_days += 1
                        if record['duration']:
                            extra_hours += record['duration'] - timedelta(hours=8) # Assuming 8 hours workday
                    elif record['status'] == 'Absent':
                        absent_days += 1
                    elif record['status'] == 'Leave Request':
                        leave_days += 1
                    elif 'DayOff' in record['status']:
                        day_offs += 1
        
        # Create a simple object to hold the summary
        class AttendanceSummary:
            def __init__(self, total_days, present_days, absent_days, leave_days, day_offs, extra_hours):
                self.total_days = total_days
                self.present_days = present_days
                self.absent_days = absent_days
                self.leave_days = leave_days
                self.day_offs = day_offs
                self.extra_hours = extra_hours

        attendance_summary = AttendanceSummary(total_days, present_days, absent_days, leave_days, day_offs, extra_hours)

        # Populate employee_data if employee_id is provided
        employee_data = User.query.get(employee_id)
    
    if start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            end_datetime_obj = datetime.combine(end_date_obj, datetime.max.time())
            
            # Limit to 2 years of data
            max_start_date = datetime.now() - timedelta(days=730)
            if start_date_obj < max_start_date:
                start_date_obj = max_start_date
            
            # Get historical logs
            query = AttendanceLog.query\
                .filter(AttendanceLog.timestamp.between(start_date_obj, end_datetime_obj))\
                .join(User)
            
            # If employee filter is applied and user is admin, or if employee is viewing their own data
            if (is_admin and employee_id) or is_employee_viewing_own_data:
                if employee_id:
                    employee_id = int(employee_id)
                else:
                    employee_id = current_user.id
                query = query.filter(AttendanceLog.user_id == employee_id)
            
            sort_order = request.args.get('sort_order', 'desc') # Default to descending


            if sort_order == 'asc':
                query = query.order_by(AttendanceLog.timestamp.asc())
            else:
                query = query.order_by(AttendanceLog.timestamp.desc())

            historical_logs = query.all()
            
            # Generate all dates in the range
            all_dates = []
            current_date = start_date_obj.date()
            while current_date <= end_date_obj.date():
                all_dates.append(current_date)
                current_date += timedelta(days=1)
            
            # Sort all_dates based on sort_order
            if sort_order == 'asc':
                all_dates.sort()
            else:
                all_dates.sort(reverse=True)
            
            # Group logs by date
            date_grouped_logs = defaultdict(list)
            for log in historical_logs:
                date_key = log.timestamp.strftime('%Y-%m-%d')
                date_grouped_logs[date_key].append(log)
            
            # Create an ordered dictionary for historical_attendance
            historical_attendance = OrderedDict()
            
            # Process each date's logs
            # Process all dates in the range, not just those with logs
            for date_obj in all_dates:
                date_key = date_obj.strftime('%Y-%m-%d')
                logs = date_grouped_logs.get(date_key, [])
                processed_historical_logs = process_attendance_logs(logs)
                historical_weekday = date_obj.weekday()
                is_historical_weekend = (historical_weekday == 4 or historical_weekday == 5)  # Friday (4) or Saturday (5)

                # Check if this date is a paid holiday
                from models import PaidHoliday
                paid_holiday = PaidHoliday.query.filter(
                    or_(
                        # Single day holiday
                        and_(PaidHoliday.holiday_type == 'day',
                             PaidHoliday.start_date == date_obj),
                        # Range holiday that includes this date
                        and_(PaidHoliday.holiday_type == 'range',
                             PaidHoliday.start_date <= date_obj,
                             PaidHoliday.end_date >= date_obj)
                    )
                ).first()



                # Create a single dictionary for all users (present and absent)
                all_users = {}
                
                for user in all_active_users:
                    # If employee filter is applied, only process that employee
                    if (is_admin and employee_id and user.id != employee_id) or (is_employee_viewing_own_data and user.id != current_user.id):
                        continue
                    
                    # Check if user's joining date is before the current date
                    if user.joining_date and date_obj < user.joining_date:
                        # Employee was not yet joined on this date
                        all_users[user.id] = {
                            'user': user,
                            'check_in': None,
                            'check_out': None,
                            'duration': None,
                            'status': 'Not Yet Joined'
                        }
                        continue
                    
                    # Check if user has a daily attendance record for this date
                    daily_record = DailyAttendance.query.filter_by(
                        user_id=user.id,
                        date=date_obj
                    ).first()
                    
                    # Check if user has an approved leave for this date
                    leave_request = LeaveRequest.query.filter(
                        LeaveRequest.user_id == user.id,
                        LeaveRequest.status == 'approved',
                        LeaveRequest.start_date <= date_obj,
                        LeaveRequest.end_date >= date_obj
                    ).first()
                    is_on_leave = leave_request is not None
                    
                    # Check if user has an approved permission for this date
                    permission_request = PermissionRequest.query.filter(
                        PermissionRequest.user_id == user.id,
                        PermissionRequest.status == 'approved',
                        func.date(PermissionRequest.start_time) == date_obj
                    ).first()
                    has_permission = permission_request is not None
                    
                    # Initialize user data
                    user_data = {
                                'user': user,
                                'check_in': None,
                                'check_out': None,
                                'duration': None,
                        'status': 'Absent'  # Default status
                    }
                    
                    # Check if user has attendance logs for this date
                    has_attendance_logs = user.id in processed_historical_logs
                    
                    if has_attendance_logs:
                        # User has attendance logs - get the processed data
                        user_data = processed_historical_logs[user.id].copy()
                        user_data['user'] = user  # Ensure user object is set
                        
                        # Handle various status combinations
                        if is_on_leave:
                            # User has logs AND is on leave - show as present with leave info
                            user_data['status'] = 'Present'
                            user_data['leave_request'] = leave_request
                            if daily_record and daily_record.leave_type_name:
                                user_data['leave_type_name'] = daily_record.leave_type_name
                                user_data['leave_type_id'] = daily_record.leave_type_id
                        elif has_permission:
                            # User has logs AND has permission - show as present with permission info
                            user_data['status'] = 'Present'
                            user_data['permission_request'] = permission_request
                        elif daily_record and daily_record.status == 'paid_holiday' and daily_record.paid_holiday_id:
                            # User has logs AND it's a paid holiday - check if holiday still exists
                            from models import PaidHoliday
                            paid_holiday = PaidHoliday.query.get(daily_record.paid_holiday_id)
                            if paid_holiday:
                                user_data['status'] = f"Present - {daily_record.holiday_name}"
                                user_data['holiday_name'] = daily_record.holiday_name
                                user_data['paid_holiday_id'] = daily_record.paid_holiday_id
                            else:
                                # Paid holiday no longer exists - clean up and show as present
                                logging.info(f"Cleaning up orphaned paid holiday record for user {user.id} on {date_obj}")
                                db.session.delete(daily_record)
                                db.session.commit()
                                user_data['status'] = 'Present'
                        elif is_historical_weekend and user_data['status'] == 'present':
                            user_data['status'] = 'DayOff / Present'
                        # If user has logs but no special status, keep as 'present'
                        elif user_data['status'] == 'present':
                            user_data['status'] = 'Present'
                    else:
                        # User has no attendance logs - determine status based on other factors
                        if is_on_leave:
                            # User is on leave but no logs
                            user_data['status'] = daily_record.leave_type_name if daily_record and daily_record.leave_type_name else 'Leave Request'
                            user_data['leave_request'] = leave_request
                            if daily_record:
                                user_data['leave_type_name'] = daily_record.leave_type_name
                                user_data['leave_type_id'] = daily_record.leave_type_id
                        elif has_permission:
                            # User has permission but no logs
                            user_data['status'] = 'Permission'
                            user_data['permission_request'] = permission_request
                        elif daily_record and daily_record.status == 'paid_holiday' and daily_record.paid_holiday_id:
                            # It's a paid holiday but user has no logs - check if holiday still exists
                            from models import PaidHoliday
                            paid_holiday = PaidHoliday.query.get(daily_record.paid_holiday_id)
                            if paid_holiday:
                                user_data['status'] = daily_record.holiday_name
                                user_data['holiday_name'] = daily_record.holiday_name
                                user_data['paid_holiday_id'] = daily_record.paid_holiday_id
                            else:
                                # Paid holiday no longer exists - clean up and show as absent
                                logging.info(f"Cleaning up orphaned paid holiday record for user {user.id} on {date_obj}")
                                db.session.delete(daily_record)
                                db.session.commit()
                                user_data['status'] = 'DayOff' if is_historical_weekend else 'Absent'
                        else:
                            # No special status - determine based on weekend
                            user_data['status'] = 'DayOff' if is_historical_weekend else 'Absent'
                    
                    all_users[user.id] = user_data

                
                # Sort all users by employee name (A-Z)
                sorted_users = {}
                if all_users:
                    user_items = list(all_users.items())
                    user_items.sort(key=lambda x: (x[1]['user'].first_name, x[1]['user'].last_name))
                    sorted_users = {user_id: data for user_id, data in user_items}
                
                # Store the attendance data along with paid holiday information
                historical_attendance[date_key] = {
                    'attendance_data': sorted_users,
                    'paid_holiday': paid_holiday.description if paid_holiday else None,
                    'is_paid_holiday': paid_holiday is not None
                }
        
        except ValueError as e:
            logging.error(f"Error processing date range: {str(e)}")

    # Prepare a dictionary to store absent days for each user
    user_absent_days = {}
    for date_key, date_data in historical_attendance.items():
        records = date_data.get('attendance_data', {})
        is_paid_holiday = date_data.get('is_paid_holiday', False)

        for record in records.values():
            # Only count as absent if it's not a paid holiday
            if record['status'] == 'Absent' and not is_paid_holiday:
                user_id = record['user'].id
                if user_id not in user_absent_days:
                    user_absent_days[user_id] = {'user': User.query.get(user_id), 'absent_dates': []}
                user_absent_days[user_id]['absent_dates'].append(date_key)

    # Get all employees for the admin filter dropdown
    employees = None
    if is_admin or current_user.role in ['manager', 'director']:
        if current_user.role == 'manager' and current_user.department_id:
            # Managers can see employees in their department
            employees = User.query.filter(
                User.status == 'active',
                User.department_id == current_user.department_id,
                ~User.first_name.like('User%'),  # Exclude generic test users
                ~User.first_name.like('NN-%'),   # Exclude numbered test users
                User.first_name != '',           # Exclude empty names
                User.last_name != ''             # Exclude users without last names
            ).order_by(User.first_name).all()
        else:
            # Admins and directors can see all employees
            employees = User.query.filter(
                User.status == 'active',
                ~User.first_name.like('User%'),  # Exclude generic test users
                ~User.first_name.like('NN-%'),   # Exclude numbered test users
                User.first_name != '',           # Exclude empty names
                User.last_name != ''             # Exclude users without last names
            ).order_by(User.first_name).all()
    
    # Debug logging for template data
    logging.info(f'Rendering template with daily_attendance: {len(daily_attendance)} entries')
    logging.info(f'Rendering template with historical_attendance: {len(historical_attendance)} entries')
    logging.info(f'Rendering template with employees: {len(employees) if employees else 0} entries')
    logging.info(f'Rendering template with employee_data: {len(employee_data) if employee_data else 0} entries')
    
    return render_template('attendance/index.html',
                          title='Daily Attendance',
                          daily_attendance=daily_attendance,
                          historical_attendance=historical_attendance,
                          employees=employees,
                          employee_data=employee_data,
                          attendance_summary=attendance_summary,
                          is_admin=is_admin,
                          today=today,
                          user_absent_days=user_absent_days)


@attendance_bp.route('/sync-fingerprint')
#@login_required
#@role_required(['admin', 'product_owner'])
def sync_fingerprint():
    """Sync attendance records from the fingerprint device with enhanced error handling"""
    try:
        device = get_active_device()
        logging.info('Starting attendance sync process...')
        logging.info(f'Attempting to sync from device: {device.device_ip}:{device.device_port}')
        logging.debug('Inside sync_fingerprint function.')
        
        # First test the connection with diagnostics
        success, diagnostics = test_device_connection()
        if not success:
            logging.error(f'Device connection test failed during sync: {diagnostics}')
            return jsonify({
                'status': 'error',
                'message': 'Device connection test failed',
                'diagnostics': diagnostics
            }), 500
        
        conn = None
        zk = ZK(device.device_ip, port=device.device_port, timeout=5)
        sync_results = {
            'records_found': 0,
            'records_added': 0,
            'unmatched_records': [],
            'errors': [],
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Attempt to connect with retry
            retries = 3
            for attempt in range(retries):
                try:
                    logging.info(f'Connection attempt {attempt + 1} to device...')
                    logging.debug(f'Attempting connection to {device.device_ip}:{device.device_port}')
                    conn = zk.connect()
                    if conn:
                        logging.info('Successfully connected to device')
                        break
                    logging.warning(f'Connection attempt {attempt + 1} failed, retrying...')
                    time.sleep(2)  # Wait before retry
                except Exception as e:
                    if attempt == retries - 1:
                        raise
                    logging.warning(f'Connection attempt {attempt + 1} failed: {str(e)}')
                    time.sleep(2)
            
            if not conn:
                error_msg = 'Failed to establish connection with the device after multiple attempts'
                sync_results['errors'].append(error_msg)
                logging.error(error_msg)
                return jsonify({
                    'status': 'error',
                    'message': error_msg,
                    'results': sync_results
                }), 500
            
            # Get attendance records
            logging.info('Retrieving attendance records...')
            attendance_records = conn.get_attendance()
            sync_results['records_found'] = len(attendance_records) if attendance_records else 0
            
            if not attendance_records:
                logging.info('No new attendance records found')
                return jsonify({
                    'status': 'success',
                    'message': 'No new attendance records found',
                    'results': sync_results
                })
            
            # Process records
            for record in attendance_records:
                try:
                    # Find user by fingerprint number
                    user = User.query.filter_by(fingerprint_number=str(record.user_id)).first()
                    if not user:
                        user = User.query.filter_by(fingerprint_number=str(record.uid)).first()
                    
                    if not user:
                        sync_results['unmatched_records'].append({
                            'device_user_id': record.user_id,
                            'device_uid': record.uid,
                            'timestamp': record.timestamp.isoformat()
                        })
                        continue
                    
                    # Check for existing record (check across all devices for same user and timestamp)
                    existing_record = AttendanceLog.query.filter_by(
                        user_id=user.id,
                        timestamp=record.timestamp
                    ).first()
                    
                    if not existing_record:
                        scan_type = determine_attendance_type(record.timestamp)
                        new_record = AttendanceLog(
                            user_id=user.id,
                            timestamp=record.timestamp,
                            device_ip=device.device_ip,
                            scan_type=scan_type
                        )
                        db.session.add(new_record)
                        sync_results['records_added'] += 1
                        
                        # Update daily attendance
                        process_daily_attendance(user.id, record.timestamp.date())
                
                except Exception as e:
                    error_msg = f'Error processing record: {str(e)}'
                    sync_results['errors'].append(error_msg)
                    logging.error(error_msg)
                    db.session.rollback()
                    continue
            
            # Commit changes
            if sync_results['records_added'] > 0:
                db.session.commit()
                logging.info(f"Successfully added {sync_results['records_added']} new records")
            
            sync_results['end_time'] = datetime.now().isoformat()
            return jsonify({
                'status': 'success',
                'message': f"Sync completed. Added {sync_results['records_added']} new records.",
                'results': sync_results
            })
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'Error during sync: {str(e)}'
            sync_results['errors'].append(error_msg)
            logging.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg,
                'results': sync_results
            }), 500
            
    except Exception as e:
        error_msg = f'Sync process failed: {str(e)}'
        logging.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg,
            'diagnostics': {'errors': [str(e)]}
        }), 500

@attendance_bp.route('/sync-device-users')
#@login_required
#@role_required(['admin', 'product_owner'])
def sync_device_users():
    """Sync users from the fingerprint device to the database"""
    try:
        success, message = sync_users_from_device()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            })
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 500
            
    except Exception as e:
        logging.error(f'Error syncing users from device: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to sync users from device'
        }), 500

@attendance_bp.route('/employee/<int:user_id>')
@login_required
def employee_attendance(user_id):
    """View employee's attendance records"""
    user = User.query.get_or_404(user_id)
    
    # Check permissions
    if current_user.is_admin() or current_user.is_product_owner() or current_user.is_director():
        # Admins, Product Owners, and directors can view any employee's attendance
        pass
    elif current_user.id == user_id:
        # Users can view their own attendance
        pass
    elif current_user.is_manager() and current_user.department_id:
        # Managers can view employees in their department
        if user.department_id != current_user.department_id:
            abort(403)
    else:
        # No permission to view this employee's attendance
        abort(403)
    
    # Get date range from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            # Default to start of current month
            today = date.today()
            start_date = date(today.year, today.month, 1)
        
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = date.today()
        
        # Get daily attendance records
        attendance_records = user.get_daily_attendance(start_date, end_date)
        
        # Get leave and permission requests for the date range
        leave_requests = LeaveRequest.query.filter(
            LeaveRequest.user_id == user.id,
            LeaveRequest.status == 'approved',
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date
        ).all()
        
        permission_requests = PermissionRequest.query.filter(
            PermissionRequest.user_id == user.id,
            PermissionRequest.status == 'approved',
            func.date(PermissionRequest.start_time) >= start_date,
            func.date(PermissionRequest.start_time) <= end_date
        ).all()
        
        # Create dictionaries for quick lookup
        leave_by_date = {}
        for leave in leave_requests:
            current_date = leave.start_date
            while current_date <= leave.end_date:
                if current_date not in leave_by_date:
                    leave_by_date[current_date] = []
                leave_by_date[current_date].append(leave)
                current_date += timedelta(days=1)
        
        permission_by_date = {}
        for permission in permission_requests:
            permission_date = permission.start_time.date()
            if permission_date not in permission_by_date:
                permission_by_date[permission_date] = []
            permission_by_date[permission_date].append(permission)
        
        # Calculate summary statistics
        total_days = (end_date - start_date).days + 1
        present_days = sum(1 for record in attendance_records if record.status == 'present')
        half_days = sum(1 for record in attendance_records if record.status == 'half-day')
        absent_days = total_days - present_days - half_days
        total_hours = sum(record.total_working_hours or 0 for record in attendance_records)
        
        # Calculate additional statistics for monthly_stats
        late_days = sum(1 for record in attendance_records if record.status == 'present' and record.is_late)
        avg_hours = total_hours / present_days if present_days > 0 else 0
        
        # Create monthly_stats object
        monthly_stats = {
            'present_days': present_days,
            'total_hours': total_hours,
            'avg_hours': avg_hours,
            'late_days': late_days
        }
        
        return render_template('attendance/employee.html',
                             user=user,
                             attendance_records=attendance_records,
                             start_date=start_date,
                             end_date=end_date,
                             total_days=total_days,
                             present_days=present_days,
                             half_days=half_days,
                             absent_days=absent_days,
                             total_hours=round(total_hours, 2),
                             monthly_stats=monthly_stats,
                             leave_by_date=leave_by_date,
                             permission_by_date=permission_by_date)
        
    except ValueError as e:
        flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
        return redirect(url_for('attendance.employee_attendance', user_id=user_id))

@attendance_bp.route('/raw-logs')
@login_required
@role_required(['admin', 'product_owner', 'manager'])
def raw_logs():
    """View raw attendance logs with filtering options"""
    # Get filter parameters
    user_id = request.args.get('user_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Build query
    query = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc())
    
    if user_id:
        query = query.filter(AttendanceLog.user_id == user_id)
    
    try:
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            start_datetime = datetime.combine(start_date, datetime.min.time())
            query = query.filter(AttendanceLog.timestamp >= start_datetime)
        
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.filter(AttendanceLog.timestamp <= end_datetime)
    except ValueError:
        flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
    
    # Get all users for the filter dropdown
    users = User.query.order_by(User.first_name).all()
    
    # Paginate results
    page = request.args.get('page', 1, type=int)
    per_page = 50
    logs = query.paginate(page=page, per_page=per_page)
    
    return render_template('attendance/raw_logs.html',
                          title='Raw Attendance Logs',
                          logs=logs,
                          users=users,
                          selected_user_id=user_id,
                          start_date=start_date.strftime('%Y-%m-%d') if start_date else '',
                          end_date=end_date.strftime('%Y-%m-%d') if end_date else '')

@attendance_bp.route('/sync-status')
#@login_required
#@role_required(['admin', 'product_owner'])
def sync_status():
    """Get the current sync status and latest records"""
    try:
        # Get the 5 most recent attendance logs from the last 5 minutes
        current_time = datetime.now()
        five_minutes_ago = current_time - timedelta(minutes=5)
        
        recent_logs = AttendanceLog.query.filter(
            AttendanceLog.timestamp >= five_minutes_ago
        ).order_by(
            AttendanceLog.timestamp.desc()
        ).limit(5).all()
        
        # Get the last sync time
        last_sync = AttendanceLog.query.order_by(
            AttendanceLog.created_at.desc()
        ).first()
        
        response_data = {
            'status': 'success',
            'last_sync': last_sync.created_at.isoformat() if last_sync else None,
            'latest_records': [{
                'user': log.user.get_full_name(),
                'timestamp': log.timestamp.strftime('%Y-%m-%d %I:%M:%S %p'),
                'scan_type': log.scan_type
            } for log in recent_logs],
            'sync_info': {
                'total_records_today': AttendanceLog.query.filter(
                    func.date(AttendanceLog.timestamp) == date.today()
                ).count(),
                'last_check_time': current_time.strftime('%Y-%m-%d %I:%M:%S %p')
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        error_msg = f'Error getting sync status: {str(e)}'
        logging.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg,
            'timestamp': datetime.now().isoformat()
        }), 500


@attendance_bp.route('/device-settings', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner'])
def device_settings():
    """Manage fingerprint device settings - Multiple devices support"""
    devices = DeviceSettings.query.order_by(DeviceSettings.created_at.desc()).all()
    form = DeviceSettingsForm()

    # Get device status for all devices
    device_statuses = {}
    for device in devices:
        device_statuses[device.id] = get_device_status(device.device_ip, device.device_port)

    return render_template('attendance/device_settings.html',
                         title='Device Settings',
                         form=form,
                         devices=devices,
                         device_statuses=device_statuses)

@attendance_bp.route('/device/add', methods=['POST'])
@login_required
@role_required(['product_owner'])  # Only Product Owner can add devices
def add_device():
    """Add a new device"""
    form = DeviceSettingsForm(request.form)
    
    # Debug: Log form data
    logging.info(f'Add device form data: {form.data}')
    logging.info(f'Form errors: {form.errors}')
    logging.info(f'Form validated: {form.validate_on_submit()}')
    logging.info(f'Request form data: {request.form}')
    logging.info(f'Request method: {request.method}')
    
    if form.validate_on_submit():
        logging.info('Form validation passed, proceeding with device creation')
        
        # Check if device with same IP and port already exists
        existing_device = DeviceSettings.query.filter_by(
            device_ip=form.device_ip.data,
            device_port=form.device_port.data
        ).first()
        
        if existing_device:
            flash('A device with this IP and port already exists!', 'error')
            logging.warning(f'Device already exists: {form.device_ip.data}:{form.device_port.data}')
            return redirect(url_for('attendance.device_settings'))
        
        try:
            device = DeviceSettings(
                device_ip=form.device_ip.data,
                device_port=form.device_port.data,
                device_name=form.device_name.data,
                is_active=form.is_active.data
            )
            
            logging.info(f'Creating device: {device.device_name} ({device.device_ip}:{device.device_port})')
            db.session.add(device)
            db.session.commit()
            flash('Device added successfully!', 'success')
            logging.info(f'Device added successfully: {device.device_name} ({device.device_ip}:{device.device_port})')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding device: {str(e)}', 'error')
            logging.error(f'Error adding device: {str(e)}')
    else:
        logging.warning('Form validation failed')
        # Log validation errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'error')
                logging.error(f'Form validation error - {field}: {error}')
        
        # If no validation errors but form didn't validate, check for missing data
        if not form.errors:
            flash('Form submission failed. Please check all fields are filled correctly.', 'error')
            logging.error('Form submission failed without validation errors')
    
    return redirect(url_for('attendance.device_settings'))

@attendance_bp.route('/device/<int:device_id>/edit', methods=['POST'])
@login_required
@role_required(['product_owner'])  # Only Product Owner can edit devices
def edit_device(device_id):
    """Edit an existing device"""
    device = DeviceSettings.query.get_or_404(device_id)
    form = DeviceSettingsForm(obj=device)
    
    if form.validate_on_submit():
        # Check if another device with same IP and port exists
        existing_device = DeviceSettings.query.filter(
            DeviceSettings.device_ip == form.device_ip.data,
            DeviceSettings.device_port == form.device_port.data,
            DeviceSettings.id != device_id
        ).first()
        
        if existing_device:
            flash('Another device with this IP and port already exists!', 'error')
            return redirect(url_for('attendance.device_settings'))
        
        device.device_ip = form.device_ip.data
        device.device_port = form.device_port.data
        device.device_name = form.device_name.data
        device.is_active = form.is_active.data
        
        db.session.commit()
        flash('Device updated successfully!', 'success')
    
    return redirect(url_for('attendance.device_settings'))

@attendance_bp.route('/device/<int:device_id>/delete', methods=['POST'])
@login_required
@role_required(['product_owner'])  # Only Product Owner can delete devices
def delete_device(device_id):
    """Delete a device"""
    device = DeviceSettings.query.get_or_404(device_id)
    
    # Check if device has attendance logs
    log_count = AttendanceLog.query.filter_by(device_id=device_id).count()
    if log_count > 0:
        # Instead of preventing deletion, we'll update the device_id to NULL for existing logs
        # and then delete the device
        try:
            # Update attendance logs to remove device reference
            AttendanceLog.query.filter_by(device_id=device_id).update({'device_id': None})
            
            
            # Delete the device
            db.session.delete(device)
            db.session.commit()
            
            flash(f'Device deleted successfully! Updated {log_count} attendance logs to remove device reference.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting device: {str(e)}', 'error')
    else:
        # No attendance logs, safe to delete
        try:
            
            # Delete the device
            db.session.delete(device)
            db.session.commit()
            
            flash('Device deleted successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting device: {str(e)}', 'error')
    
    return redirect(url_for('attendance.device_settings'))


@attendance_bp.route('/test-connection')
@login_required
@role_required(['admin', 'product_owner'])
def test_connection():
    """Test connection to a specific device"""
    device_ip = request.args.get('device_ip')
    device_port = request.args.get('device_port', type=int)
    
    if not device_ip or not device_port:
        return jsonify({
            'status': 'error',
            'message': 'Device IP and port are required'
        }), 400
    
    try:
        device_status = get_device_status(device_ip, device_port)
        if device_status['connected']:
            return jsonify({
                'status': 'success',
                'message': f'Successfully connected to {device_ip}:{device_port}',
                'device_info': device_status.get('device_info', {})
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to connect to {device_ip}:{device_port}. {device_status.get("error", "Unknown error")}'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error testing connection: {str(e)}'
        }), 500

def create_system_user_from_device_user(device_user_data, device_user_id):
    """Automatically create a system user from device user data"""
    try:
        from werkzeug.security import generate_password_hash
        import secrets
        import string
        
        # Generate a temporary email and password
        device_name = device_user_data.get('name', f'User{device_user_id}')
        base_email = f"{device_name.lower().replace(' ', '.')}@company.com"
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        
        # Check if email already exists, if so, add a number
        email = base_email
        counter = 1
        while User.query.filter_by(email=email).first():
            email = f"{base_email.split('@')[0]}{counter}@company.com"
            counter += 1
        
        # Create the system user
        new_user = User(
            first_name=device_name or f"User{device_user_id}",
            last_name="",  # Will be filled by user later
            email=email,
            password_hash=generate_password_hash(temp_password),
            fingerprint_number=device_user_id,
            role='employee',  # Default role
            status='active',
            department_id=None  # Will be assigned later
        )
        
        db.session.add(new_user)
        db.session.flush()  # Get the new user ID
        
        logging.info(f'Auto-created system user: {new_user.first_name} ({email}) with fingerprint {device_user_id}')
        
        return new_user
        
    except Exception as e:
        logging.error(f'Error auto-creating system user for device user {device_user_id}: {str(e)}')
        db.session.rollback()
        return None

def sync_device_users_to_table(device):
    """Sync users from a device to the DeviceUser table"""
    try:
        logging.info(f'Syncing users from device {device.get_display_name()} to DeviceUser table')
        
        # Get device status and users
        device_status = get_device_status(device.device_ip, device.device_port)
        
        if not device_status['connected']:
            logging.error(f'Cannot connect to device {device.get_display_name()}')
            return False
        
        device_info = device_status.get('device_info', {})
        users = device_info.get('users', [])
        
        if not users:
            logging.info(f'No users found on device {device.get_display_name()}')
            return True
        
        # Get existing device users for this device
        existing_device_users = DeviceUser.query.filter_by(device_id=device.id).all()
        existing_user_ids = {str(du.device_user_id) for du in existing_device_users}
        
        # Get system users for matching
        system_users = User.query.filter(User.fingerprint_number.isnot(None)).all()
        system_fingerprint_numbers = {str(user.fingerprint_number) for user in system_users}
        
        users_added = 0
        users_updated = 0
        
        for user in users:
            device_user_id = str(user.get('user_id', ''))
            
            # Check if this user already exists in DeviceUser table
            existing_device_user = DeviceUser.query.filter_by(
                device_id=device.id,
                device_user_id=device_user_id
            ).first()
            
            # Check if this user exists in system by fingerprint number
            system_user = next((u for u in system_users if str(u.fingerprint_number) == device_user_id), None)
            
            # If no system user found by fingerprint, check if there's already a processed device user with same fingerprint
            if not system_user:
                existing_processed_device_user = DeviceUser.query.filter_by(
                    device_user_id=device_user_id,
                    is_processed=True
                ).first()
                if existing_processed_device_user:
                    system_user = User.query.get(existing_processed_device_user.system_user_id)
            
            if existing_device_user:
                # If no system user exists, automatically create one
                if not system_user:
                    system_user = create_system_user_from_device_user(user, device_user_id)
                    if system_user:
                        logging.info(f'Auto-created system user for existing device user {device_user_id}: {system_user.first_name}')
                
                # Update existing record
                existing_device_user.device_name = user.get('name')
                existing_device_user.privilege = user.get('privilege')
                existing_device_user.group_id = user.get('group_id')
                existing_device_user.card = user.get('card')
                existing_device_user.system_user_id = system_user.id if system_user else None
                existing_device_user.is_processed = system_user is not None
                existing_device_user.updated_at = datetime.utcnow()
                users_updated += 1
            else:
                # If no system user exists, automatically create one
                if not system_user:
                    system_user = create_system_user_from_device_user(user, device_user_id)
                    if system_user:
                        logging.info(f'Auto-created system user for device user {device_user_id}: {system_user.first_name}')
                
                # Create new DeviceUser record
                device_user = DeviceUser(
                    device_id=device.id,
                    device_user_id=device_user_id,
                    device_uid=user.get('uid'),
                    device_name=user.get('name'),
                    privilege=user.get('privilege'),
                    group_id=user.get('group_id'),
                    card=user.get('card'),
                    system_user_id=system_user.id if system_user else None,
                    is_processed=system_user is not None
                )
                db.session.add(device_user)
                users_added += 1
        
        db.session.commit()
        logging.info(f'Synced users from {device.get_display_name()}: {users_added} added, {users_updated} updated')
        return True
        
    except Exception as e:
        logging.error(f'Error syncing users from device {device.get_display_name()}: {str(e)}')
        db.session.rollback()
        return False

@attendance_bp.route('/device/<int:device_id>/users')
@login_required
@role_required(['admin', 'product_owner', 'director'])  # Allow all users who can view device settings
def device_users(device_id):
    """Get users from a specific device"""
    try:
        device = DeviceSettings.query.get_or_404(device_id)
        
        # Get device status and users
        device_status = get_device_status(device.device_ip, device.device_port)
        
        if not device_status['connected']:
            return jsonify({
                'status': 'error',
                'message': f'Cannot connect to device {device.get_display_name()}. Error: {device_status.get("error", "Unknown error")}'
            }), 500
        
        device_info = device_status.get('device_info', {})
        users = device_info.get('users', [])
        
        # Check which users are already in our system
        system_users = User.query.filter(User.fingerprint_number.isnot(None)).all()
        system_fingerprint_numbers = {str(user.fingerprint_number) for user in system_users}
        
        # Categorize users
        existing_users = []
        new_users = []
        
        for user in users:
            user_id = str(user.get('user_id', ''))
            if user_id in system_fingerprint_numbers:
                # Find the system user
                system_user = next((u for u in system_users if str(u.fingerprint_number) == user_id), None)
                existing_users.append({
                    'device_user_id': user.get('user_id'),
                    'device_uid': user.get('uid'),
                    'device_name': user.get('name'),
                    'system_user_id': system_user.id if system_user else None,
                    'system_user_name': system_user.get_full_name() if system_user else None,
                    'privilege': user.get('privilege'),
                    'group_id': user.get('group_id'),
                    'card': user.get('card')
                })
            else:
                new_users.append({
                    'device_user_id': user.get('user_id'),
                    'device_uid': user.get('uid'),
                    'device_name': user.get('name'),
                    'privilege': user.get('privilege'),
                    'group_id': user.get('group_id'),
                    'card': user.get('card')
                })
        
        return jsonify({
            'status': 'success',
            'device_name': device.get_display_name(),
            'total_users': len(users),
            'existing_users': existing_users,
            'new_users': new_users,
            'device_info': {
                'firmware_version': device_info.get('firmware_version'),
                'serial_number': device_info.get('serial_number'),
                'platform': device_info.get('platform'),
                'device_name': device_info.get('device_name')
            }
        })
        
    except Exception as e:
        logging.error(f'Error getting device users: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving users: {str(e)}'
        }), 500


@attendance_bp.route('/sync-device')
@login_required
@role_required(['admin', 'product_owner'])
def sync_device():
    """Sync data from a specific device"""
    device_id = request.args.get('device_id', type=int)
    device_ip = request.args.get('device_ip')
    device_port = request.args.get('device_port', type=int)
    
    if not device_id or not device_ip or not device_port:
        return jsonify({
            'status': 'error',
            'message': 'Device ID, IP, and port are required'
        }), 400
    
    try:
        # Get the device
        device = DeviceSettings.query.get(device_id)
        if not device:
            return jsonify({
                'status': 'error',
                'message': 'Device not found'
            }), 404
        
        # Sync data from this specific device
        sync_stats = sync_attendance_from_device(device)
        
        return jsonify({
            'status': 'success',
            'message': f'Synced {sync_stats.get("records_added", 0)} records from {device.get_display_name()}',
            'stats': sync_stats
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error syncing device: {str(e)}'
        }), 500

@attendance_bp.route('/fetch-all-devices-data', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def fetch_all_devices_data():
    """Comprehensive endpoint to fetch all types of data from all devices"""
    try:
        # Get all active devices
        active_devices = DeviceSettings.query.filter_by(is_active=True).all()
        if not active_devices:
            return jsonify({
                'status': 'error',
                'message': 'No active devices found. Please add and activate devices in Device Settings.',
                'devices_found': 0
            }), 400

        device_names = [device.get_display_name() for device in active_devices]
        logging.info(f'Comprehensive data fetch requested for {len(active_devices)} active devices: {", ".join(device_names)}')

        # Initialize results structure
        results = {
            'devices_processed': 0,
            'total_devices': len(active_devices),
            'attendance_records': {'added': 0, 'updated': 0, 'total': 0},
            'users_data': {'added': 0, 'updated': 0, 'total': 0},
            'device_status': [],
            'device_results': [],
            'summary': {},
            'errors': []
        }

        # Process each device
        for device in active_devices:
            device_result = {
                'device_id': device.id,
                'device_name': device.get_display_name(),
                'device_ip': device.device_ip,
                'device_port': device.device_port,
                'status': 'processing',
                'data_types': {},
                'errors': []
            }

            try:
                # 1. Get device status and connection info
                logging.info(f'Fetching status for device: {device.get_display_name()}')
                device_status = get_device_status(device.device_ip, device.device_port)
                device_result['connection_status'] = device_status
                
                if device_status['connected']:
                    device_result['status'] = 'connected'
                    
                    # 2. Fetch attendance data
                    try:
                        logging.info(f'Syncing attendance data from: {device.get_display_name()}')
                        attendance_sync = sync_attendance_from_device(device)
                        device_result['data_types']['attendance'] = attendance_sync
                        
                        if attendance_sync.get('status') == 'success':
                            results['attendance_records']['added'] += attendance_sync.get('records_added', 0)
                            results['attendance_records']['updated'] += attendance_sync.get('records_updated', 0)
                    except Exception as e:
                        error_msg = f'Attendance sync failed: {str(e)}'
                        device_result['errors'].append(error_msg)
                        logging.error(f'Device {device.get_display_name()} - {error_msg}')

                    # 3. Fetch users data
                    try:
                        logging.info(f'Syncing users data from: {device.get_display_name()}')
                        users_sync = sync_device_users_to_table(device)
                        device_result['data_types']['users'] = {'success': users_sync}
                        
                        if users_sync:
                            # Count users for this device
                            device_users = DeviceUser.query.filter_by(device_id=device.id).count()
                            results['users_data']['total'] += device_users
                    except Exception as e:
                        error_msg = f'Users sync failed: {str(e)}'
                        device_result['errors'].append(error_msg)
                        logging.error(f'Device {device.get_display_name()} - {error_msg}')

                    # 4. Get device information and statistics
                    try:
                        device_info = device_status.get('device_info', {})
                        device_result['data_types']['device_info'] = {
                            'users_count': len(device_info.get('users', [])),
                            'records_count': device_info.get('records_count', 0),
                            'device_time': device_info.get('device_time'),
                            'firmware_version': device_info.get('firmware_version'),
                            'serial_number': device_info.get('serial_number')
                        }
                    except Exception as e:
                        error_msg = f'Device info fetch failed: {str(e)}'
                        device_result['errors'].append(error_msg)
                        logging.error(f'Device {device.get_display_name()} - {error_msg}')

                    device_result['status'] = 'completed' if not device_result['errors'] else 'completed_with_errors'
                else:
                    device_result['status'] = 'connection_failed'
                    error_msg = f'Cannot connect to device: {device_status.get("error", "Unknown error")}'
                    device_result['errors'].append(error_msg)
                    results['errors'].append(f'{device.get_display_name()}: {error_msg}')

            except Exception as e:
                device_result['status'] = 'failed'
                error_msg = f'Device processing failed: {str(e)}'
                device_result['errors'].append(error_msg)
                results['errors'].append(f'{device.get_display_name()}: {error_msg}')
                logging.error(f'Error processing device {device.get_display_name()}: {str(e)}')

            results['device_results'].append(device_result)
            results['devices_processed'] += 1

        # Calculate totals and summary
        results['attendance_records']['total'] = results['attendance_records']['added'] + results['attendance_records']['updated']
        
        successful_devices = len([d for d in results['device_results'] if d['status'] in ['completed', 'completed_with_errors']])
        connected_devices = len([d for d in results['device_results'] if d['connection_status']['connected']])
        
        results['summary'] = {
            'total_devices': len(active_devices),
            'devices_processed': results['devices_processed'],
            'successful_connections': connected_devices,
            'successful_data_fetch': successful_devices,
            'total_attendance_records': results['attendance_records']['total'],
            'total_users_synced': results['users_data']['total'],
            'has_errors': len(results['errors']) > 0
        }

        # Determine overall status
        if successful_devices == len(active_devices):
            overall_status = 'success'
            message = f'Successfully fetched data from all {len(active_devices)} devices'
        elif successful_devices > 0:
            overall_status = 'partial_success'
            message = f'Fetched data from {successful_devices}/{len(active_devices)} devices'
        else:
            overall_status = 'failed'
            message = f'Failed to fetch data from any devices'

        return jsonify({
            'status': overall_status,
            'message': message,
            **results
        })

    except Exception as e:
        logging.error(f'Error in comprehensive device data fetch: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': f'System error during data fetch: {str(e)}',
            'devices_processed': 0
        }), 500

@attendance_bp.route('/manual-entry', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner', 'manager'])
def manual_entry():
    """Handle manual attendance entry"""
    if request.method == 'POST':
        try:
            user_id = request.form.get('user_id')
            entry_type = request.form.get('entry_type')  # 'check-in' or 'check-out'
            timestamp = request.form.get('timestamp')
            reason = request.form.get('reason')
            failure_id = request.form.get('failure_id')
            
            if not all([user_id, entry_type, timestamp]):
                flash('All fields are required', 'error')
                return redirect(url_for('attendance.manual_entry'))
            
            # Convert timestamp string to datetime
            timestamp = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M')
            
            # Create attendance log
            new_log = AttendanceLog(
                user_id=user_id,
                timestamp=timestamp,
                scan_type=entry_type,
                device_ip='MANUAL',
                manual_entry=True,
                manual_entry_reason=reason
            )
            db.session.add(new_log)
            
            # If this is resolving a failure, mark it as resolved
            if failure_id:
                failure = FingerPrintFailure.query.get(failure_id)
                if failure:
                    failure.resolved = True
                    failure.manual_entry = True
                    failure.resolution_note = f"Manual entry by {current_user.get_full_name()}: {reason}"
            
            # Update daily attendance
            process_daily_attendance(user_id, timestamp.date())
            
            db.session.commit()
            flash('Manual attendance entry recorded successfully', 'success')
            return redirect(url_for('attendance.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording manual entry: {str(e)}', 'error')
            return redirect(url_for('attendance.manual_entry'))
    
    # GET request - show form
    users = User.query.order_by(User.first_name).all()
    unresolved_failures = FingerPrintFailure.query.filter_by(resolved=False).order_by(FingerPrintFailure.timestamp.desc()).all()
    
    return render_template('attendance/manual_entry.html',
                         users=users,
                         unresolved_failures=unresolved_failures)

@attendance_bp.route('/fingerprint-failures')
@login_required
@role_required(['admin', 'product_owner', 'manager'])
def fingerprint_failures():
    """View fingerprint failure logs and statistics"""
    # Get date range from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start_date = datetime.now() - timedelta(days=30)  # Default to last 30 days
        
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            end_date = datetime.combine(end_date, datetime.max.time())
        else:
            end_date = datetime.now()
        
        # Get failure logs
        query = FingerPrintFailure.query
        
        if start_date and end_date:
            query = query.filter(FingerPrintFailure.timestamp.between(start_date, end_date))
        
        failures = query.order_by(FingerPrintFailure.timestamp.desc()).all()
        
        # Calculate statistics
        stats = defaultdict(lambda: {
            'total_failures': 0,
            'unread': 0,
            'no_match': 0,
            'device_error': 0,
            'resolved': 0,
            'manual_entries': 0
        })
        
        for failure in failures:
            if failure.employee_id:
                stats[failure.employee_id]['total_failures'] += 1
                stats[failure.employee_id][failure.error_type] += 1
                if failure.resolved:
                    stats[failure.employee_id]['resolved'] += 1
                if failure.manual_entry:
                    stats[failure.employee_id]['manual_entries'] += 1
        
        # Get user information for each employee_id
        users = User.query.filter(User.fingerprint_number.in_(stats.keys())).all()
        user_map = {user.fingerprint_number: user for user in users}
        
        return render_template('attendance/fingerprint_failures.html',
                             failures=failures,
                             stats=stats,
                             user_map=user_map,
                             start_date=start_date,
                             end_date=end_date)
                             
    except Exception as e:
        flash(f'Error retrieving fingerprint failure logs: {str(e)}', 'error')
        return redirect(url_for('attendance.index'))

@attendance_bp.route('/my-attendance')
@login_required
def my_attendance():
    """View personal or all attendance records based on user role"""
    # Redirect employees to the main attendance page to see their detailed logs
    if current_user.role == 'employee':
        return redirect(url_for('attendance.index'))
    
    try:
        # Get date range from query parameters
        view_type = request.args.get('view', 'daily')  # daily, weekly, monthly
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        selected_user_id = request.args.get('user_id', type=int)
        
        logging.info(f'Fetching attendance for view_type={view_type}, start_date={start_date}, end_date={end_date}, selected_user_id={selected_user_id}')
        
        try:
            if start_date:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                if view_type == 'daily':
                    start_date = date.today()
                elif view_type == 'weekly':
                    start_date = date.today() - timedelta(days=7)
                else:  # monthly
                    start_date = date.today().replace(day=1)
            
            if end_date:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            else:
                end_date = date.today()
            
            logging.info(f'Date range: {start_date} to {end_date}')
            
        except ValueError as e:
            logging.error(f'Date parsing error: {str(e)}')
            flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
            return redirect(url_for('attendance.my_attendance'))
        
        # Initialize variables
        users = []
        attendance_records = {}
        today_logs = {}
        summary_stats = {}
        active_leaves = {}
        active_permissions = {}
        
        if current_user.is_admin() or current_user.is_product_owner() or current_user.is_director():
            # Admin/Product Owner/Director view - show all users or selected user
            users = User.query.order_by(User.first_name).all()
            logging.info(f'Found {len(users)} total users')
            
            if selected_user_id:
                user_ids = [selected_user_id]
                selected_user = User.query.get(selected_user_id)
                if not selected_user:
                    logging.error(f'Selected user ID {selected_user_id} not found')
                    flash('Selected user not found.', 'error')
                    return redirect(url_for('attendance.my_attendance'))
            else:
                # For admin/product_owner/director, show all users by default
                user_ids = [user.id for user in users]
        elif current_user.is_manager():
            # Manager view - show team members or selected user
            if current_user.department_id:
                users = User.query.filter_by(status='active', department_id=current_user.department_id).order_by(User.first_name).all()
                logging.info(f'Found {len(users)} team members')
                
                if selected_user_id:
                    # Check if selected user is in manager's department
                    selected_user = User.query.get(selected_user_id)
                    if not selected_user or selected_user.department_id != current_user.department_id:
                        logging.error(f'Selected user ID {selected_user_id} not found or not in manager\'s department')
                        flash('Selected user not found or not in your team.', 'error')
                        return redirect(url_for('attendance.my_attendance'))
                    user_ids = [selected_user_id]
                else:
                    # Show all team members by default
                    user_ids = [user.id for user in users]
            else:
                # Manager with no department - show only themselves
                user_ids = [current_user.id]
                users = [current_user]
                logging.info(f'Manager with no department - showing only themselves: {current_user.get_full_name()}')
        else:
            # Regular user view - show only their attendance
            user_ids = [current_user.id]
            users = [current_user]
            logging.info(f'Regular user view for: {current_user.get_full_name()}')
        
        # Process attendance records for all relevant users
        for user_id in user_ids:
            try:
                # Create a list of all dates in the range
                date_list = []
                current_date = start_date
                while current_date <= end_date:
                    date_list.append(current_date)
                    current_date += timedelta(days=1)
                
                # Get existing daily attendance records
                existing_records = DailyAttendance.query.filter(
                    DailyAttendance.user_id == user_id,
                    DailyAttendance.date.between(start_date, end_date)
                ).all()
                
                # Get today's attendance logs to check for check-ins that haven't been processed yet
                today_attendance_logs = AttendanceLog.query.filter(
                    AttendanceLog.user_id == user_id,
                    func.date(AttendanceLog.timestamp) == date.today(),
                    AttendanceLog.scan_type == 'check-in'
                ).all()
                
                # Create a dictionary for quick lookup
                existing_records_dict = {record.date: record for record in existing_records}
                
                # Create a complete list of records for all dates
                user_records_for_display = []
                for current_date in date_list:
                    if current_date in existing_records_dict:
                        # Use existing record
                        user_records_for_display.append(existing_records_dict[current_date])
                    else:
                        # Create a placeholder record
                        placeholder = DailyAttendance()
                        placeholder.user_id = user_id
                        placeholder.date = current_date
                        
                        # Mark weekends as day_off
                        if current_date.weekday() in [4, 5]:  # 4 = Friday, 5 = Saturday
                            placeholder.status = 'day_off'
                        # For today, check if there are any check-ins before marking as absent
                        elif current_date == date.today() and today_attendance_logs:
                            placeholder.status = 'present'
                            placeholder.first_check_in = today_attendance_logs[0].timestamp
                        else:
                            placeholder.status = 'absent'
                        
                        user_records_for_display.append(placeholder)
                
                # Sort records by date (newest first)
                user_records_for_display.sort(key=lambda x: x.date, reverse=True)
                
                # Store the complete list of records
                attendance_records[user_id] = user_records_for_display
                
                # Get today's raw attendance logs for detailed timeline
                if view_type == 'daily' and start_date == date.today():
                    user_today_logs = AttendanceLog.query.filter(
                        AttendanceLog.user_id == user_id,
                        func.date(AttendanceLog.timestamp) == date.today()
                    ).order_by(AttendanceLog.timestamp).all()
                    logging.info(f'Found {len(user_today_logs)} today logs for user {user_id}')
                    today_logs[user_id] = user_today_logs
                
                # Calculate summary statistics
                total_days = (end_date - start_date).days + 1
                
                # Count existing records - any record with logs is treated as present
                present_days = sum(1 for r in existing_records if r.status in ['present', 'half-day', 'partial'] or r.first_check_in or r.last_check_out)
                # Add today if there are check-ins but no daily record yet
                if date.today() >= start_date and date.today() <= end_date and today_attendance_logs and date.today() not in existing_records_dict:
                    present_days += 1
                
                half_days = 0  # No longer counting half-days separately
                existing_day_offs = sum(1 for r in existing_records if r.status == 'day_off')
                absent_days = sum(1 for r in existing_records if r.status == 'absent')
                total_hours = sum(r.total_working_hours or 0 for r in existing_records)
                
                # Count weekend days in the date range for day_offs
                weekend_days = sum(1 for d in date_list if d.weekday() in [4, 5])
                
                # Total day offs is existing records plus weekends that don't have records
                day_offs = existing_day_offs + weekend_days - sum(1 for r in existing_records if r.status == 'day_off' and r.date.weekday() in [4, 5])
                
                # Calculate average hours only for days when the user was present (including all attendance types)
                present_days_count = sum(1 for r in existing_records if r.status in ['present', 'half-day', 'partial'] or r.first_check_in or r.last_check_out)
                avg_hours = total_hours / present_days_count if present_days_count > 0 else 0
                
                summary_stats[user_id] = {
                    'total_days': total_days,
                    'present_days': present_days,
                    'half_days': half_days,
                    'day_offs': day_offs,
                    'absent_days': absent_days,
                    'total_hours': round(total_hours, 2),
                    'avg_hours': round(avg_hours, 2)
                }
                
                # Get active leaves and permissions
                active_leave = LeaveRequest.query.filter(
                    LeaveRequest.user_id == user_id,
                    LeaveRequest.start_date <= date.today(),
                    LeaveRequest.end_date >= date.today(),
                    LeaveRequest.status == 'approved'
                ).first()
                
                active_permission = PermissionRequest.query.filter(
                    PermissionRequest.user_id == user_id,
                    func.date(PermissionRequest.start_time) == date.today(),
                    PermissionRequest.status == 'approved'
                ).first()
                
                if active_leave:
                    active_leaves[user_id] = active_leave
                if active_permission:
                    active_permissions[user_id] = active_permission
                    
            except Exception as e:
                logging.error(f'Error processing user {user_id}: {str(e)}')
                continue
        
        return render_template('attendance/my_attendance.html',
                             view_type=view_type,
                             start_date=start_date,
                             end_date=end_date,
                             users=users,
                             selected_user_id=selected_user_id,
                             attendance_records=attendance_records,
                             today_logs=today_logs,
                             summary_stats=summary_stats,
                             active_leaves=active_leaves,
                             active_permissions=active_permissions,
                             auto_refresh=True,
                             user_joining_date=current_user.joining_date)  # Enable auto-refresh
                             
    except Exception as e:
        logging.error(f'Unexpected error in my_attendance: {str(e)}')
        flash('An error occurred while fetching attendance records.', 'error')
        return redirect(url_for('dashboard.index'))

@attendance_bp.route('/my-attendance/sync-status')
@login_required
def my_attendance_sync_status():
    """Get personal attendance sync status and latest records"""
    try:
        # Get today's latest attendance logs
        today_logs = AttendanceLog.query.filter(
            AttendanceLog.user_id == current_user.id,
            func.date(AttendanceLog.timestamp) == date.today()
        ).order_by(AttendanceLog.timestamp.desc()).limit(5).all()
        
        return jsonify({
            'status': 'success',
            'latest_records': [{
                'timestamp': log.timestamp.strftime('%Y-%m-%d %I:%M:%S %p'),
                'scan_type': log.scan_type,
                'duration': log.format_duration() if log.duration else None
            } for log in today_logs]
        })
                
    except Exception as e:
        logging.error(f'Error getting personal sync status: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': 'Failed to get sync status'
        }), 500

# Add a new route for AJAX updates
@attendance_bp.route('/attendance-updates')
@login_required
def attendance_updates():
    """Get attendance updates for AJAX refresh"""
    try:
        user_id = request.args.get('user_id', type=int)
        if current_user.is_admin() or (user_id and user_id == current_user.id):
            # Get today's latest logs
            today_logs = AttendanceLog.query.filter(
                AttendanceLog.user_id == user_id if user_id else True,
                func.date(AttendanceLog.timestamp) == date.today()
            ).order_by(AttendanceLog.timestamp.desc()).all()
            
            # Format the logs for JSON response
            logs_data = [{
                'user_name': log.user.get_full_name(),
                'timestamp': log.timestamp.strftime('%I:%M %p'),
                'scan_type': log.scan_type,
                'device_ip': log.device_ip
            } for log in today_logs]
            
            return jsonify({
                'status': 'success',
                'logs': logs_data
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized'
            }), 403
            
    except Exception as e:
        logging.error(f'Error getting attendance updates: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@attendance_bp.route('/user-stats')
@login_required
def user_stats():
    """Get user attendance stats for AJAX updates"""
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'User ID is required'
            }), 400
            
        # Check permissions
        if not current_user.is_admin() and current_user.id != user_id:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized'
            }), 403
            
        # Get today's date
        today = date.today()
        
        # Get daily attendance records for the current month
        month_start = today.replace(day=1)
        user_records = DailyAttendance.query.filter(
            DailyAttendance.user_id == user_id,
            DailyAttendance.date.between(month_start, today)
        ).all()
        
        # Calculate statistics
        total_days = (today - month_start).days + 1
        present_days = sum(1 for r in user_records if r.status == 'present')
        half_days = sum(1 for r in user_records if r.status == 'half-day')
        absent_days = total_days - present_days - half_days
        total_hours = sum(r.total_working_hours or 0 for r in user_records)
        avg_hours = total_hours / len(user_records) if user_records else 0
        
        return jsonify({
            'status': 'success',
            'present_days': present_days,
            'half_days': half_days,
            'absent_days': absent_days,
            'total_hours': round(total_hours, 2),
            'avg_hours': round(avg_hours, 2)
        })
        
    except Exception as e:
        logging.error(f'Error getting user stats: {str(e)}')
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Add a new diagnostic endpoint
@attendance_bp.route('/device-diagnostics')
#@login_required
#@role_required(['admin', 'product_owner'])
def device_diagnostics():
    """Run comprehensive device diagnostics"""
    success, diagnostics = test_device_connection()
    return jsonify({
        'status': 'success' if success else 'error',
        'message': 'Device diagnostics completed',
        'diagnostics': diagnostics
    })






@attendance_bp.route('/force-sync', methods=['POST'])
#@login_required
#@role_required(['admin', 'product_owner'])
def force_sync():
    """Force sync all attendance records from device"""
    try:
        logging.info('Starting force sync process...')
        
        # First test the connection
        success, diagnostics = test_device_connection()
        if not success:
            error_msg = f'Device connection failed: {diagnostics.get("details", ["Connection failed"])[0]}'
            logging.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg,
                'timestamp': datetime.now().isoformat()
            }), 500

        # Run the sync task in a try-except block
        try:
            sync_stats = sync_attendance_task(full_sync=True)
            
            # Get the latest sync results from the last 5 minutes
            five_minutes_ago = datetime.now() - timedelta(minutes=5)
            latest_logs = AttendanceLog.query.filter(
                AttendanceLog.timestamp >= five_minutes_ago
            ).order_by(
                AttendanceLog.timestamp.desc()
            ).all()
            
            # Get the last sync time
            last_sync = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc()).first()
            
            response_data = {
                'status': 'success',
                'message': 'Attendance sync completed successfully',
                'timestamp': datetime.now().isoformat(),
                'last_sync': last_sync.timestamp.isoformat() if last_sync else None,
                'latest_records': [{
                    'user': log.user.get_full_name(),
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %I:%M:%S %p'),
                    'scan_type': log.scan_type
                } for log in latest_logs],
                'sync_info': {
                    'total_records_today': AttendanceLog.query.filter(
                        func.date(AttendanceLog.timestamp) == date.today()
                    ).count()
                }
            }
            
            logging.info('Manual sync completed successfully')
            return jsonify(response_data)
            
        except Exception as e:
            error_msg = f'Sync task failed: {str(e)}'
            logging.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg,
                'timestamp': datetime.now().isoformat()
            }), 500
            
    except Exception as e:
        error_msg = f'Manual sync failed: {str(e)}'
        logging.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg,
            'timestamp': datetime.now().isoformat()
        }), 500

def get_device_status(device_ip, device_port):
    """Get basic device status for a specific IP and port"""
    device_status = {
        'connected': False,
        'device_info': None,
        'last_sync': None,
        'error': None
    }
    
    try:
        zk = ZK(device_ip, port=device_port, timeout=5)
        conn = zk.connect()
        if conn:
            device_status['connected'] = True
            try:
                # Get basic device information
                device_info = {}
                device_info['firmware_version'] = conn.get_firmware_version()
                device_info['serial_number'] = conn.get_serialnumber()
                device_info['platform'] = conn.get_platform()
                device_info['device_name'] = conn.get_device_name()
                
                # Get users and convert to serializable format
                try:
                    users = conn.get_users()
                    device_info['users'] = [
                        {
                            'uid': user.uid,
                            'name': user.name,
                            'privilege': user.privilege,
                            'password': user.password,
                            'group_id': user.group_id,
                            'user_id': user.user_id,
                            'card': user.card
                        } for user in users
                    ] if users else []
                except Exception as e:
                    logging.warning(f'Error getting users: {str(e)}')
                    device_info['users'] = []
                
                device_status['device_info'] = device_info
            except Exception as e:
                logging.warning(f'Error getting device info: {str(e)}')
            finally:
                conn.disconnect()
        else:
            device_status['error'] = 'Could not connect to device'
    except Exception as e:
        device_status['error'] = str(e)
        logging.error(f'Error connecting to device {device_ip}:{device_port}: {str(e)}')
    
    return device_status

def get_device_status_info():
    """Get detailed device status including firmware version and user count"""
    logging.info('get_device_status called.')
    device = get_active_device()
    device_status = {
        'connected': False,
        'device_info': None,
        'last_sync': None,
        'error': None
    }
    
    if not device:
        device_status['error'] = 'No active device settings found.'
        logging.error('No active device settings found for get_device_status.')
        return device_status

    logging.info(f'Attempting to connect to device at {device.device_ip}:{device.device_port}')
    
    try:
        zk = ZK(device.device_ip, port=device.device_port, timeout=5)
        conn = None
        
        try:
            conn = zk.connect()
            if conn:
                device_status['connected'] = True
                logging.info('Successfully connected to device.')
                try:
                    # Get device information with proper error handling for each call
                    device_info = {}
                    
                    try:
                        device_info['firmware_version'] = conn.get_firmware_version()
                    except Exception as e:
                        device_info['firmware_version'] = 'Unknown'
                        logging.warning(f'Error getting firmware version: {str(e)}')
                    
                    try:
                        device_info['serial_number'] = conn.get_serialnumber()
                    except Exception as e:
                        device_info['serial_number'] = 'Unknown'
                        logging.warning(f'Error getting serial number: {str(e)}')
                    
                    try:
                        device_info['platform'] = conn.get_platform()
                    except Exception as e:
                        device_info['platform'] = 'Unknown'
                        logging.warning(f'Error getting platform: {str(e)}')
                    
                    try:
                        device_info['device_name'] = conn.get_device_name() or 'X628-TC/ID'
                    except Exception as e:
                        device_info['device_name'] = 'X628-TC/ID'
                        logging.warning(f'Error getting device name: {str(e)}')
                    
                    try:
                        users = conn.get_users()
                        device_info['users'] = len(users) if users else 0
                    except Exception as e:
                        device_info['users'] = 0
                        logging.warning(f'Error getting users: {str(e)}')
                    
                    device_status['device_info'] = device_info
                    logging.info(f'Device info retrieved: {device_info}')
                    
                    # Get last sync time
                    last_log = AttendanceLog.query.order_by(AttendanceLog.created_at.desc()).first()
                    if last_log:
                        device_status['last_sync'] = last_log.created_at.isoformat()
                        logging.info(f'Last sync time: {device_status["last_sync"]}')
                    
                except Exception as e:
                    device_status['error'] = f'Error retrieving device information: {str(e)}'
                    logging.error(f'Error retrieving device information: {str(e)}')
                
            else:
                logging.warning('ZK connection object is None after connect attempt.')
        except Exception as e:
            device_status['error'] = f'Error connecting to device: {str(e)}'
            logging.error(f'Error connecting to device: {str(e)}')
            
        finally:
            if conn:
                try:
                    conn.disconnect()
                    logging.info('Disconnected from device.')
                except Exception as e:
                    logging.warning(f'Error disconnecting from device: {str(e)}')
                
    except Exception as e:
        device_status['error'] = f'Error initializing device connection: {str(e)}'
        logging.error(f'Error initializing device connection: {str(e)}')
    
    logging.info(f'Final device_status: {device_status}')
    return device_status







def get_realtime_employee_status():
    """Get real-time employee check-in/out status from the fingerprint device"""
    try:
        device_ip = '192.168.11.2'
        device_port = 4370
        
        # Get today's date range
        today = datetime.now().date()
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.now()
        
        # Get all users with fingerprint numbers
        users_dict = {str(user.fingerprint_number): user for user in User.query.all() if user.fingerprint_number}
        
        # Connect to device
        zk = ZK(device_ip, port=device_port, timeout=30)
        conn = None
        employee_status = []
        
        try:
            conn = zk.connect()
            if not conn:
                raise Exception('Could not connect to device')
            
            # Get attendance records from device
            attendance_records = conn.get_attendance()
            if attendance_records:
                # Filter today's records and sort by timestamp
                today_records = [
                    record for record in attendance_records 
                    if start_datetime <= record.timestamp <= end_datetime
                ]
                today_records.sort(key=lambda x: x.timestamp, reverse=True)
                
                # Process each user's latest record
                processed_users = set()
                for record in today_records:
                    user_id = str(record.user_id)
                    if user_id not in processed_users:
                        user = users_dict.get(user_id)
                        if user:
                            # Get user's latest record for today
                            latest_log = AttendanceLog.query.filter(
                                AttendanceLog.user_id == user.id,
                                AttendanceLog.timestamp.between(start_datetime, end_datetime)
                            ).order_by(AttendanceLog.timestamp.desc()).first()
                            
                            status = {
                                'user_id': user.id,
                                'name': user.get_full_name(),
                                'status': 'Unknown',
                                'last_scan': None,
                                'duration': None
                            }
                            
                            if latest_log:
                                status['last_scan'] = latest_log.timestamp.strftime('%Y-%m-%d %I:%M:%S %p')
                                status['status'] = 'In Office' if latest_log.scan_type == 'check-in' else 'Out of Office'
                                if latest_log.duration:
                                    status['duration'] = latest_log.format_duration()
                            
                            employee_status.append(status)
                            processed_users.add(user_id)
                
        except Exception as e:
            logging.error(f'Error getting real-time status: {str(e)}')
            raise
        
        finally:
            if conn:
                conn.disconnect()
                
        return employee_status
        
    except Exception as e:
        logging.error(f'Failed to get employee status: {str(e)}')
        return []

@attendance_bp.route('/realtime-status')
@login_required
def realtime_status():
    """Get real-time employee check-in/out status"""
    try:
        status = get_realtime_employee_status()
        return jsonify({
            'status': 'success',
            'data': status,
            'timestamp': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
        }), 500

# Add new route for full sync
@attendance_bp.route('/full-sync', methods=['POST'])
#@login_required
#@role_required(['admin', 'product_owner'])
def full_sync():
    """Perform a full sync of all attendance records"""
    try:
        logging.info('Starting full sync process...')
        sync_stats = sync_attendance_task(full_sync=True)
        
        if sync_stats:
            return jsonify({
                'status': 'success',
                'message': f"Full sync completed. Added {sync_stats['records_added']} new records.",
                'stats': sync_stats
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Full sync failed to complete'
            }), 500
            
    except Exception as e:
        error_msg = f'Full sync failed: {str(e)}'
        logging.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg
        }), 500

@attendance_bp.route('/reprocess-attendance', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def reprocess_attendance_data():
    """Re-process attendance data for specific user and date range"""
    try:
        from datetime import datetime, date, timedelta
        from models import User, DailyAttendance, AttendanceLog
        
        # Get parameters from request
        user_id = request.json.get('user_id') if request.json else request.form.get('user_id')
        start_date_str = request.json.get('start_date') if request.json else request.form.get('start_date')
        end_date_str = request.json.get('end_date') if request.json else request.form.get('end_date')
        
        if not all([user_id, start_date_str, end_date_str]):
            return jsonify({
                'success': False,
                'message': 'Missing required parameters: user_id, start_date, end_date'
            }), 400
        
        # Parse dates
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # Get user
        user = User.query.get(int(user_id))
        if not user:
            return jsonify({
                'success': False,
                'message': f'User with ID {user_id} not found'
            }), 404
        
        processed_count = 0
        current_date = start_date
        
        while current_date <= end_date:
            # Check if there are logs for this date
            start_datetime = datetime.combine(current_date, datetime.min.time())
            end_datetime = datetime.combine(current_date, datetime.max.time())
            
            logs = AttendanceLog.query.filter(
                AttendanceLog.user_id == user_id,
                AttendanceLog.timestamp.between(start_datetime, end_datetime)
            ).all()
            
            if logs:
                # Delete existing DailyAttendance record
                existing_record = DailyAttendance.query.filter_by(
                    user_id=user_id,
                    date=current_date
                ).first()
                
                if existing_record:
                    db.session.delete(existing_record)
                    db.session.flush()
                
                # Re-process the attendance for this date
                new_record = process_daily_attendance(user_id, current_date)
                
                if new_record:
                    db.session.commit()
                    processed_count += 1
                    logging.info(f"Reprocessed {current_date} for user {user.get_full_name()}: Check-in: {new_record.first_check_in}, Check-out: {new_record.last_check_out}")
            
            current_date += timedelta(days=1)
        
        return jsonify({
            'success': True,
            'message': f'Successfully reprocessed {processed_count} days for {user.get_full_name()}',
            'processed_count': processed_count
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error reprocessing attendance data: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error reprocessing attendance: {str(e)}'
        }), 500
