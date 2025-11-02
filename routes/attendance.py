from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, abort
from flask_apscheduler import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from flask_login import login_required, current_user
from models import db, User, AttendanceLog, DailyAttendance, LeaveRequest, PermissionRequest, FingerPrintFailure, DeviceSettings
from helpers import role_required, sync_users_from_device
from forms import DeviceSettingsForm
from datetime import datetime, timedelta, date
from zk import ZK
import logging
from collections import defaultdict, OrderedDict
from sqlalchemy import func
import socket
import time
import threading
import json
import subprocess
import platform

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
    if (request.endpoint 
        and request.endpoint.startswith('attendance.') 
        and request.endpoint not in ['attendance.my_attendance', 'attendance.my_attendance_sync_status']
        and not current_app.config.get('IS_ADMIN_INSTANCE', False)):
        flash('This feature is only available on the admin portal.', 'error')
        return redirect(url_for('dashboard.index'))

# Apply protection to admin routes
@attendance_bp.before_request
def before_request():
    return protect_admin_routes()

def format_duration(duration):
    """Format timedelta into hours and minutes"""
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def determine_attendance_type(timestamp):
    """Determine if a timestamp is for check-in or check-out based on time of day"""
    hour = timestamp.hour
    minute = timestamp.minute
    
    # Early morning to noon is always check-in (4 AM - 12 PM)
    if 4 <= hour < 12:
        return 'check-in'
    
    # Noon to 2 PM - likely check-in for afternoon shift
    if 12 <= hour <= 14:
        return 'check-in'
    
    # Late afternoon/evening is check-out (2 PM - 11 PM)
    if 14 < hour <= 23:
        return 'check-out'
    
    # Very late night/early morning (11 PM - 4 AM) defaults to check-out
    return 'check-out'

def process_attendance_logs(logs):
    """Process attendance logs to group by user and determine check-in/check-out"""
    user_logs = {}
    
    for log in logs:
        if log.user_id not in user_logs:
            user_logs[log.user_id] = {
                'user': log.user,
                'check_in': None,
                'check_out': None,
                'duration': None,
                'status': 'absent'  # Default status
            }

            
        log_type = determine_attendance_type(log.timestamp)
        if log_type == 'check-in' and (not user_logs[log.user_id]['check_in'] or 
                                      log.timestamp < user_logs[log.user_id]['check_in'].timestamp):
            user_logs[log.user_id]['check_in'] = log
            # Update status to "In Office" if no check-out
            user_logs[log.user_id]['status'] = 'in_office'
            
        elif log_type == 'check-out' and (not user_logs[log.user_id]['check_out'] or 
                                         log.timestamp > user_logs[log.user_id]['check_out'].timestamp):
            user_logs[log.user_id]['check_out'] = log
            
        # Calculate duration and update status if both check-in and check-out exist
        if user_logs[log.user_id]['check_in'] and user_logs[log.user_id]['check_out']:
            duration = user_logs[log.user_id]['check_out'].timestamp - user_logs[log.user_id]['check_in'].timestamp
            user_logs[log.user_id]['duration'] = format_duration(duration)
            user_logs[log.user_id]['status'] = 'present'
    
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
        date=attendance_date.date()
    ).first()
    
    if not daily_record:
        daily_record = DailyAttendance(
            user_id=user_id,
            date=attendance_date.date()
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
        if daily_record.total_working_hours >= 9:
            daily_record.status = 'present'
        elif daily_record.total_working_hours >= 4.5:
            daily_record.status = 'half-day'
        else:
            daily_record.status = 'partial'
    
    db.session.commit()
    return daily_record

def process_daily_attendance(user_id, attendance_date):
    """Process all attendance logs for a user on a specific date"""
    # Get all logs for this user on this date, ordered by timestamp
    daily_logs = AttendanceLog.query.filter(
        AttendanceLog.user_id == user_id,
        func.date(AttendanceLog.timestamp) == attendance_date
    ).order_by(AttendanceLog.timestamp).all()

    user = User.query.get(user_id)
    if user and user.joining_date and attendance_date.date() < user.joining_date:
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
    
    # Process check-in/check-out pairs
    total_working_minutes = 0
    total_break_minutes = 0
    entry_pairs = 0
    last_check_in = None
    has_active_check_in = False
    first_check_in = None
    last_check_out = None
    
    for log in daily_logs:
        if log.scan_type == 'check-in':
            if not first_check_in or log.timestamp < first_check_in:
                first_check_in = log.timestamp
            last_check_in = log
            has_active_check_in = True
        elif log.scan_type == 'check-out' and last_check_in:
            if not last_check_out or log.timestamp > last_check_out:
                last_check_out = log.timestamp
            duration = int((log.timestamp - last_check_in.timestamp).total_seconds() / 60)
            total_working_minutes += duration
            entry_pairs += 1
            has_active_check_in = False
            last_check_in = None
    
    # Determine status and reason
    status = 'absent'
    status_reason = None
    
    if leave_request:
        status = 'leave'
        status_reason = f"Approved Leave: {leave_request.reason[:50]}..."
    elif permission_request:
        status = 'permission'
        duration = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
        status_reason = f"Approved Permission ({duration:.1f}h): {permission_request.reason[:30]}..."
    elif has_active_check_in:
        status = 'in_office'
        status_reason = "Currently in office"
    elif first_check_in and last_check_out:
        total_hours = total_working_minutes / 60
        if total_hours >= 9:  # Updated to 9 hours standard workday
            status = 'present'
        elif total_hours >= 4:
            status = 'half-day'
        else:
            status = 'partial'
    elif first_check_in:
        status = 'in_office'
        status_reason = "Currently in office"
    
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
    daily_record.total_working_hours = total_working_minutes / 60
    daily_record.total_breaks = total_break_minutes
    daily_record.entry_count = entry_pairs
    daily_record.status = status
    daily_record.status_reason = status_reason
    
    return daily_record

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
        zk = ZK(device_ip, port=device_port, timeout=5)
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
    try:
        failure = FingerPrintFailure(
            error_type=error_type,
            error_message=error_message,
            device_ip=device_ip,
            employee_id=employee_id,
            raw_device_data=json.dumps(raw_data) if raw_data else None
        )
        db.session.add(failure)
        db.session.commit()
        
        # Create notification for admin
        from models import Notification
        admin_users = User.query.filter_by(role='admin').all()
        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                title='Fingerprint Read Failure',
                message=f'Fingerprint read failed: {error_type} - {error_message[:100]}...',
                notification_type='fingerprint_failure',
                related_id=failure.id
            )
            db.session.add(notification)
        db.session.commit()
        
        return failure
    except Exception as e:
        logging.error(f"Failed to log fingerprint failure: {str(e)}")
        db.session.rollback()
        return None

def sync_attendance_task(full_sync=False):
    """Sync attendance data from fingerprint device"""
    conn = None
    try:
        # Sync users from device first
        sync_users_from_device()

        # Get device settings
        device = get_active_device()
        if not device:
            error_msg = 'No active device settings found'
            logging.error(error_msg)
            log_fingerprint_failure('config_error', error_msg, None)
            return {
                'status': 'error',
                'message': error_msg
            }
        
        # Connect to device
        logging.info(f'Connecting to device {device.device_ip}:{device.device_port}...')
        zk = ZK(device.device_ip, port=device.device_port, timeout=5)
        conn = zk.connect()
        if not conn:
            error_msg = 'Could not connect to device'
            logging.error(error_msg)
            log_fingerprint_failure('connection_error', error_msg, device.device_ip)
            return {
                'status': 'error',
                'message': error_msg
            }
        
        # Get attendance records from device
        attendance_records = conn.get_attendance()
        if not attendance_records:
            return {
                'status': 'success',
                'message': 'No new records found',
                'records_added': 0
            }
        
        # Process records
        records_added = 0
        processed_dates = set()  # Track unique user-date combinations
        
        for record in attendance_records:
            # Find user by fingerprint number
            user = User.query.filter_by(fingerprint_number=str(record.user_id)).first()
            if not user:
                continue

            # Create new attendance log
            attendance_log = AttendanceLog(
                user_id=user.id,
                timestamp=record.timestamp,
                scan_type=determine_attendance_type(record.timestamp),
                device_ip=device.device_ip
            )
            
            # Check if record already exists based on user_id and timestamp
            existing_record = AttendanceLog.query.filter_by(
                user_id=attendance_log.user_id,
                timestamp=attendance_log.timestamp
            ).first()
            
            if existing_record:
                continue

            db.session.add(attendance_log)
            records_added += 1
            processed_dates.add((user.id, record.timestamp.date()))
        
        # Commit every 5 records to avoid large transactions
        if records_added % 5 == 0:
            db.session.commit()
    
        # Commit remaining records
        if records_added % 5 != 0:
            db.session.commit()
    
        # Update daily attendance for each affected user-date combination
        for user_id, attendance_date in processed_dates:
            try:
                # Pass the new logic to process_daily_attendance
                process_daily_attendance(user_id, attendance_date)
                db.session.commit()
            except Exception as e:
                logging.error(f'Error updating daily attendance: {str(e)}')
                db.session.rollback()
        
        return {
            'status': 'success',
            'message': f'Successfully added {records_added} new records',
            'records_added': records_added
        }
        
    except Exception as e:
        error_msg = f'Error syncing attendance: {str(e)}'
        logging.error(error_msg)
        log_fingerprint_failure('sync_error', error_msg, device.device_ip if 'device' in locals() else None)
        return {
            'status': 'error',
            'message': error_msg
        }
    finally:
        if conn:
                conn.disconnect()
            

@attendance_bp.route('/last-fingerprint-reading')
@login_required
@role_required('admin')
def last_fingerprint_reading():
    last_reading = AttendanceLog.query.order_by(AttendanceLog.timestamp.desc()).first()
    if last_reading:
        message = f"Last Fingerprint Reading: {last_reading.timestamp} for User ID: {last_reading.user_id} (Scan Type: {last_reading.scan_type})"
    else:
        message = "No fingerprint readings found."
    flash(message, 'info')
    return redirect(url_for('dashboard.index'))

@attendance_bp.route('/manual-sync', methods=['POST'])
@login_required
@role_required('admin')
def manual_sync():
    """Manually trigger attendance synchronization"""
    if not current_app.config.get('IS_ADMIN_INSTANCE', False):
        return jsonify({'status': 'error', 'message': 'This feature is only available on the admin portal.'}), 403

    # Check scheduler status
    scheduler = current_app.apscheduler
    if scheduler.running:
        # Check if sync_attendance_task is already running
        for job in scheduler.get_jobs():
            if job.id == 'sync_attendance_job' and job.state == STATE_RUNNING:
                return jsonify({'status': 'info', 'message': 'Automatic sync is already running. Please wait.'}), 200

    # Test device connection before attempting sync
    connected, diagnostics = test_device_connection()
    if not connected:
        return jsonify({
            'status': 'error',
            'message': 'Device not connected. Please check device settings and network.',
            'diagnostics': diagnostics
        }), 500

    # Run sync in a separate thread to avoid blocking the request
    threading.Thread(target=sync_attendance_task, args=(True,)).start()
    return jsonify({'status': 'success', 'message': 'Sync initiated successfully.'})


@attendance_bp.route('/')
#@login_required
#@role_required('admin')
def index():
    """Show the attendance page with today's records and historical data"""
    # Get today's date range
    today = datetime.now().date()
    start_datetime = datetime.combine(today, datetime.min.time())
    end_datetime = datetime.combine(today, datetime.max.time())
    
    # Get today's attendance logs
    today_logs = AttendanceLog.query\
        .filter(AttendanceLog.timestamp.between(start_datetime, end_datetime))\
        .order_by(AttendanceLog.timestamp.desc())\
        .all()
    
    # Get all active users with fingerprint numbers, sorted Z to A
    all_active_users = User.query.filter_by(status='active').filter(User.fingerprint_number != None).order_by(User.first_name.desc(), User.last_name.desc()).all()

    # Process today's logs
    processed_logs = process_attendance_logs(today_logs)

    daily_attendance = {}
    today_weekday = today.weekday() # Monday is 0, Sunday is 6
    is_weekend = (today_weekday == 4 or today_weekday == 5) # Friday is 4, Saturday is 5

    # Create two separate dictionaries for present and absent users
    present_users = {}
    absent_users = {}

    for user in all_active_users:
        # Check if user has an approved leave for today
        is_on_leave = LeaveRequest.query.filter(
            LeaveRequest.user_id == user.id,
            LeaveRequest.status == 'approved',
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today
        ).first() is not None
        
        if user.id in processed_logs:
            # User has attendance logs
            user_data = processed_logs[user.id]
            if is_on_leave:
                user_data['status'] = 'Leave Request'
            elif is_weekend and user_data['status'] == 'present':
                user_data['status'] = 'DayOff / Present'
            present_users[user.id] = user_data
        else:
            # User has no attendance logs for today
            if is_on_leave:
                status = 'Leave Request'
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
    
    # Check if user is admin and employee filter is applied
    is_admin = current_user.is_authenticated and current_user.is_admin()
    
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
            
            # If employee filter is applied and user is admin
            if is_admin and employee_id:
                employee_id = int(employee_id)
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
                is_historical_weekend = (historical_weekday == 4 or historical_weekday == 5)



                # Create two separate dictionaries for present and absent users
                present_users = {}
                absent_users = {}
                
                for user in all_active_users:
                    # If employee filter is applied, only process that employee
                    if is_admin and employee_id and user.id != employee_id:
                        continue
                    
                    # Check if user has an approved leave for this date
                    is_on_leave = LeaveRequest.query.filter(
                        LeaveRequest.user_id == user.id,
                        LeaveRequest.status == 'approved',
                        LeaveRequest.start_date <= date_obj,
                        LeaveRequest.end_date >= date_obj
                    ).first() is not None
                        
                    if user.id in processed_historical_logs:
                        user_data = processed_historical_logs[user.id]
                        if is_on_leave:
                            user_data['status'] = 'Leave Request'
                        elif is_historical_weekend and user_data['status'] == 'present':
                            user_data['status'] = 'DayOff / Present'
                        present_users[user.id] = user_data
                    else:
                        # Determine status based on weekend and leave status
                        if is_on_leave:
                            status = 'Leave Request'
                        else:
                            status = 'DayOff' if is_historical_weekend else 'Absent'
                            
                        absent_users[user.id] = {
                            'user': user,
                            'check_in': None,
                            'check_out': None,
                            'duration': None,
                            'status': status
                        }

                
                # Sort present users by employee name (A-Z)
                sorted_present_users = {}
                if present_users:
                    present_items = list(present_users.items())
                    present_items.sort(key=lambda x: (x[1]['user'].first_name, x[1]['user'].last_name))
                    sorted_present_users = {user_id: data for user_id, data in present_items}
                
                # Sort absent users by employee name (A-Z)
                sorted_absent_users = {}
                if absent_users:
                    absent_items = list(absent_users.items())
                    absent_items.sort(key=lambda x: (x[1]['user'].first_name, x[1]['user'].last_name))
                    sorted_absent_users = {user_id: data for user_id, data in absent_items}
                
                # Combine the dictionaries with sorted present users first, then sorted absent users
                historical_attendance[date_key] = {**sorted_present_users, **sorted_absent_users}
        
        except ValueError as e:
            logging.error(f"Error processing date range: {str(e)}")

    # Prepare a dictionary to store absent days for each user
    user_absent_days = {}
    for date_key, records in historical_attendance.items():
        for record in records.values():

            if record['status'] == 'Absent':
                user_id = record['user'].id
                if user_id not in user_absent_days:
                    user_absent_days[user_id] = {'user': User.query.get(user_id), 'absent_dates': []}
                user_absent_days[user_id]['absent_dates'].append(date_key)

    # Get all employees for the admin filter dropdown
    employees = None
    if is_admin:
        employees = User.query.filter_by(status='active').order_by(User.first_name).all()
    
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

@attendance_bp.route('/test-connection')
#@login_required
#@role_required('admin')
def test_connection():
    """Test connection to the fingerprint device"""
    success, message = test_device_connection()
    return jsonify({
        'status': 'success' if success else 'error',
        'message': message
    })

@attendance_bp.route('/sync-fingerprint')
#@login_required
#@role_required('admin')
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
                    
                    # Check for existing record
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
#@role_required('admin')
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
    if not (current_user.is_admin() or current_user.is_manager() or current_user.id == user_id):
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
        
        # Calculate summary statistics
        total_days = (end_date - start_date).days + 1
        present_days = sum(1 for record in attendance_records if record.status == 'present')
        half_days = sum(1 for record in attendance_records if record.status == 'half-day')
        absent_days = total_days - present_days - half_days
        total_hours = sum(record.total_working_hours or 0 for record in attendance_records)
        
        return render_template('attendance/employee.html',
                             user=user,
                             attendance_records=attendance_records,
                             start_date=start_date,
                             end_date=end_date,
                             total_days=total_days,
                             present_days=present_days,
                             half_days=half_days,
                             absent_days=absent_days,
                             total_hours=round(total_hours, 2))
        
    except ValueError as e:
        flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
        return redirect(url_for('attendance.employee_attendance', user_id=user_id))

@attendance_bp.route('/raw-logs')
@login_required
@role_required(['admin', 'manager'])
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
#@role_required('admin')
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
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'scan_type': log.scan_type
            } for log in recent_logs],
            'sync_info': {
                'total_records_today': AttendanceLog.query.filter(
                    func.date(AttendanceLog.timestamp) == date.today()
                ).count(),
                'last_check_time': current_time.strftime('%Y-%m-%d %H:%M:%S')
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


@login_required
@role_required('admin')
def device_settings():
    """Manage fingerprint device settings"""
    device = get_active_device()
    form = DeviceSettingsForm(obj=device)

    if form.validate_on_submit():
        device.device_ip = form.device_ip.data
        device.device_port = form.device_port.data
        device.device_name = form.device_name.data
        device.is_active = form.is_active.data
        db.session.add(device)
        db.session.commit()
        flash('Device settings updated successfully!', 'success')
        return redirect(url_for('attendance.device_settings'))

    return render_template('attendance/device_settings.html', title='Device Settings', form=form)

@attendance_bp.route('/manual-entry', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'manager'])
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
@role_required(['admin', 'manager'])
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
        
        if current_user.is_admin():
            # Admin view - show all users or selected user
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
                # For admin, show all users by default
                user_ids = [user.id for user in users]
        else:
            # Regular user view - show only their attendance
            user_ids = [current_user.id]
            users = [current_user]
            logging.info(f'Regular user view for: {current_user.get_full_name()}')
        
        # Process attendance records for all relevant users
        for user_id in user_ids:
            try:
                # Get daily attendance records
                user_records = DailyAttendance.query.filter(
                    DailyAttendance.user_id == user_id,
                    DailyAttendance.date.between(start_date, end_date)
                ).order_by(DailyAttendance.date.desc()).all()
                
                logging.info(f'Found {len(user_records)} attendance records for user {user_id}')
                attendance_records[user_id] = user_records
                
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
                present_days = sum(1 for r in user_records if r.status == 'present')
                half_days = sum(1 for r in user_records if r.status == 'half-day')
                absent_days = total_days - present_days - half_days
                total_hours = sum(r.total_working_hours or 0 for r in user_records)
                avg_hours = total_hours / len(user_records) if user_records else 0
                
                summary_stats[user_id] = {
                    'total_days': total_days,
                    'present_days': present_days,
                    'half_days': half_days,
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
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
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
#@role_required('admin')
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
#@role_required('admin')
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
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
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
        zk = ZK(device_ip, port=device_port, timeout=5)
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
                                status['last_scan'] = latest_log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
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
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

# Add new route for full sync
@attendance_bp.route('/full-sync', methods=['POST'])
#@login_required
#@role_required('admin')
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
@attendance_bp.route('/device-settings', methods=['GET', 'POST'])
@login_required
def device_settings():
    """Manage fingerprint device settings"""
    device = get_active_device()
    form = DeviceSettingsForm(obj=device)
    
    # Only allow admin users to modify settings
    if request.method == 'POST' and current_user.is_admin():
        if form.validate_on_submit():
            try:
                device.device_ip = form.device_ip.data
                device.device_port = form.device_port.data
                device.device_name = form.device_name.data
                device.updated_at = datetime.utcnow()
                
                db.session.commit()
                flash('Device settings updated successfully.', 'success')
                
                # Test connection with new settings
                success, diagnostics = test_device_connection()
                if not success:
                    flash(f'Warning: Could not connect to device with new settings: {diagnostics}', 'warning')
                    
                return redirect(url_for('attendance.device_settings'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating device settings: {str(e)}', 'danger')
    elif request.method == 'POST':
        flash('You do not have permission to modify device settings.', 'error')
        return redirect(url_for('attendance.device_settings'))
    
    # Get device status
    device_status = get_device_status_info()
    
    return render_template('attendance/device_settings.html',
                          title='Device Settings',
                          form=form,
                          device=device,
                          device_status=device_status)
