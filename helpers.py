from datetime import datetime, date, timedelta
from functools import wraps
from flask import flash, redirect, url_for, abort, request
from flask_login import current_user
from models import LeaveRequest, PermissionRequest, User, SMTPConfiguration
from extensions import db
from zk import ZK, const
import logging
from datetime import date, datetime, timedelta

def role_required(*roles):
    """Decorator that checks if the current user has one of the required roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Flatten roles if they are passed as lists
            allowed_roles = []
            for role in roles:
                if isinstance(role, (list, tuple)):
                    allowed_roles.extend(role)
                else:
                    allowed_roles.append(role)
            
            if current_user.role not in allowed_roles:
                # Check if this message was already flashed recently
                from flask import session
                import time
                
                permission_key = f'permission_denied_{request.endpoint}'
                current_time = time.time()
                
                # Clean up old permission denial records (older than 5 minutes)
                keys_to_remove = []
                for key in session.keys():
                    if key.startswith('permission_denied_') and isinstance(session[key], (int, float)):
                        if current_time - session[key] > 300:  # 5 minutes
                            keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    session.pop(key, None)
                
                # Only flash message if we haven't shown it recently
                if permission_key not in session or current_time - session.get(permission_key, 0) > 300:
                    flash('You do not have permission to access this page.', 'danger')
                    session[permission_key] = current_time
                
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator that checks if the current user is an admin or product owner."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role not in ['admin', 'product_owner']:
            flash('You do not have administrative privileges to access this page.', 'danger')
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def get_leave_count(user_id, period='monthly'):
    """Get the count of approved leaves for a user in the current month/year."""
    today = date.today()
    
    if period == 'monthly':
        # Start and end of current month
        start_date = date(today.year, today.month, 1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)
    else:  # yearly
        # Start and end of current year
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
        
    leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.status == 'approved',
        ((LeaveRequest.start_date <= end_date) & (LeaveRequest.end_date >= start_date))
    ).all()
    
    # Calculate total days (count each day of leave)
    total_days = 0
    for leave in leaves:
        # Calculate overlap with the period
        overlap_start = max(leave.start_date, start_date)
        overlap_end = min(leave.end_date, end_date)
        
        # Calculate days in the overlap period
        delta = (overlap_end - overlap_start).days + 1
        total_days += max(0, delta)
    
    return total_days

def get_permission_count(user_id, period='monthly'):
    """Get the count of approved permissions for a user in the current month."""
    today = date.today()
    
    # Start and end of current month
    start_date = datetime(today.year, today.month, 1)
    if today.month == 12:
        end_date = datetime(today.year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end_date = datetime(today.year, today.month + 1, 1) - timedelta(seconds=1)
    
    permissions = PermissionRequest.query.filter(
        PermissionRequest.user_id == user_id,
        PermissionRequest.status == 'approved',
        ((PermissionRequest.start_time <= end_date) & (PermissionRequest.end_time >= start_date))
    ).count()
    
    return permissions


def get_user_managers(user):
    """Get the managers for a user (direct manager, admin, and director), with department-specific filtering."""
    managers = {
        'direct_manager': None,
        'admin_managers': [],
        'department_admin_managers': [],
        'directors': []
    }
    
    # CASE 1: First check if there's a department manager assigned
    if user.department and user.department.manager_id:
        department_manager = User.query.get(user.department.manager_id)
        if department_manager and department_manager.status == 'active':
            managers['direct_manager'] = department_manager
    
    # CASE 2: If no department manager, look for any manager in the same department by role
    if not managers['direct_manager'] and user.department_id:
        dept_managers = User.query.filter_by(
            department_id=user.department_id,
            role='manager',
            status='active'
        ).all()
        
        if dept_managers:
            # Just use the first manager found in the department
            managers['direct_manager'] = dept_managers[0]
    
    # CASE 3: If there's still no direct manager, look for managers that have this employee's department in their managed_department
    if not managers['direct_manager']:
        # Find all managers in the system
        all_managers = User.query.filter_by(role='manager', status='active').all()
        
        for manager in all_managers:
            # Check if this manager has managed departments
            if hasattr(manager, 'managed_department') and manager.managed_department:
                # Get IDs of departments this manager manages
                managed_dept_ids = [dept.id for dept in manager.managed_department]
                
                # If user's department is managed by this manager, assign them
                if user.department_id and user.department_id in managed_dept_ids:
                    managers['direct_manager'] = manager
                    break
    
    # Get all admin and product owner users
    all_admins = User.query.filter(User.role.in_(['admin', 'product_owner']), User.status == 'active').all()
    managers['admin_managers'] = all_admins
    
    # Filter admins by department, if applicable
    if user.department:
        for admin in all_admins:
            if admin.managed_department:
                # Check if this admin manages the user's department
                admin_managed_depts = [dept.id for dept in admin.managed_department]
                if user.department.id in admin_managed_depts:
                    managers['department_admin_managers'].append(admin)
    
    # Get all directors
    managers['directors'] = User.query.filter_by(role='director', status='active').all()
    
    return managers

def get_employees_for_manager(manager_id):
    """Get all employees that report to a specific manager."""
    from models import Department
    
    manager = User.query.get(manager_id)
    if not manager:
        return []
    
    employees = []
    
    # Special case for admin and product owner users - they should see all employees
    if manager.role in ['admin', 'product_owner']:
        # Return all active employees in the system
        return User.query.filter(User.status == 'active', User.id != manager_id).all()
    
    # CASE 1: If this user is officially assigned as a department manager
    departments = Department.query.filter_by(manager_id=manager_id).all()
    for dept in departments:
        dept_employees = User.query.filter_by(department_id=dept.id, status='active').all()
        employees.extend(dept_employees)
    
    # CASE 2: If this user has a manager role but is not officially assigned as department manager
    if manager.role == 'manager':
        # Find all employees in the same department as this manager
        if manager.department_id:
            dept_employees = User.query.filter_by(
                department_id=manager.department_id, 
                status='active'
            ).filter(User.id != manager_id).all()
            
            # Add them to the list if not already present
            for emp in dept_employees:
                if emp not in employees:
                    employees.append(emp)
    
    return employees

def leave_request_to_dict(leave_request):
    """Convert a LeaveRequest object to a dictionary for JSON serialization."""
    return {
        'id': leave_request.id,
        'start_date': leave_request.start_date.strftime('%Y-%m-%d'),
        'end_date': leave_request.end_date.strftime('%Y-%m-%d'),
        'status': leave_request.status,
        'reason': leave_request.reason,
        'created_at': leave_request.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'manager_status': leave_request.manager_status,
        'admin_status': leave_request.admin_status,
        'manager_comment': leave_request.manager_comment,
        'admin_comment': leave_request.admin_comment
    }

def permission_request_to_dict(permission_request):
    """Convert a PermissionRequest object to a dictionary for JSON serialization."""
    return {
        'id': permission_request.id,
        'start_time': permission_request.start_time.strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': permission_request.end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'status': permission_request.status,
        'reason': permission_request.reason,
        'created_at': permission_request.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'admin_status': permission_request.admin_status,
        'admin_comment': permission_request.admin_comment,
        'admin_updated_at': permission_request.admin_updated_at.strftime('%Y-%m-%d %H:%M:%S') if permission_request.admin_updated_at else None
    }

def get_dashboard_stats(user):
    """Get statistics for the dashboard based on user role."""
    stats = {
        'pending_leave_requests': 0,
        'pending_permission_requests': 0,
        'approved_leave_requests': 0,
        'approved_permission_requests': 0,
        'rejected_leave_requests': 0,
        'rejected_permission_requests': 0,
        'total_employees': 0,
        'total_departments': 0,
        'leave_balances': []
    }
    
    if user.role == 'employee':
        # Employee sees only their own stats
        stats['pending_leave_requests'] = LeaveRequest.query.filter_by(
            user_id=user.id, status='pending'
        ).count()
        
        stats['pending_permission_requests'] = PermissionRequest.query.filter_by(
            user_id=user.id, status='pending'
        ).count()
        
        stats['approved_leave_requests'] = LeaveRequest.query.filter_by(
            user_id=user.id, status='approved'
        ).count()
        
        stats['approved_permission_requests'] = PermissionRequest.query.filter_by(
            user_id=user.id, status='approved'
        ).count()
        
        stats['rejected_leave_requests'] = LeaveRequest.query.filter_by(
            user_id=user.id, status='rejected'
        ).count()
        
        stats['rejected_permission_requests'] = PermissionRequest.query.filter_by(
            user_id=user.id, status='rejected'
        ).count()
        
    elif user.role == 'manager':
        # Manager sees stats for their department
        employees = get_employees_for_manager(user.id)
        employee_ids = [emp.id for emp in employees]
        
        if employee_ids:  # Only query if there are employees
            stats['pending_leave_requests'] = LeaveRequest.query.filter(
                LeaveRequest.user_id.in_(employee_ids),
                LeaveRequest.status == 'pending',
                LeaveRequest.manager_status == 'pending'
            ).count()
            
            stats['pending_permission_requests'] = PermissionRequest.query.filter(
                PermissionRequest.user_id.in_(employee_ids),
                PermissionRequest.status == 'pending',
                PermissionRequest.admin_status == 'pending'
            ).count()
            
            # Get approved requests from manager's team
            stats['approved_leave_requests'] = LeaveRequest.query.filter(
                LeaveRequest.user_id.in_(employee_ids),
                LeaveRequest.status == 'approved'
            ).count()
            
            stats['approved_permission_requests'] = PermissionRequest.query.filter(
                PermissionRequest.user_id.in_(employee_ids),
                PermissionRequest.status == 'approved'
            ).count()
            
            # Get team attendance statistics for today
            from models import DailyAttendance
            from datetime import date
            today = date.today()
            
            # Count team members present today
            stats['team_present_today'] = DailyAttendance.query.filter(
                DailyAttendance.date == today,
                DailyAttendance.user_id.in_(employee_ids),
                DailyAttendance.status.in_(['present', 'half-day', 'in_office'])
            ).count()
            
            # Count team members absent today
            stats['team_absent_today'] = len(employee_ids) - stats['team_present_today']
            
            stats['total_employees'] = len(employee_ids)
        else:
            # If manager has no employees, set defaults
            stats['team_present_today'] = 0
            stats['team_absent_today'] = 0
        
        
    elif user.role in ['admin', 'product_owner']:
        # Admin sees all pending requests (simplified for better UX)
        stats['pending_leave_requests'] = LeaveRequest.query.filter_by(status='pending').count()
        
        # All pending permission requests
        stats['pending_permission_requests'] = PermissionRequest.query.filter_by(status='pending').count()
        
        # All approved leave requests
        stats['approved_leave_requests'] = LeaveRequest.query.filter_by(status='approved').count()
        
        # All approved permission requests
        stats['approved_permission_requests'] = PermissionRequest.query.filter_by(status='approved').count()
        
        # All rejected leave requests
        stats['rejected_leave_requests'] = LeaveRequest.query.filter_by(status='rejected').count()
        
        # All rejected permission requests
        stats['rejected_permission_requests'] = PermissionRequest.query.filter_by(status='rejected').count()
        
        # Count all employees (excluding admins) with fingerprint numbers
        stats['total_employees'] = User.query.filter(
            User.status == 'active', 
            User.role.notin_(['admin', 'product_owner']),
            User.fingerprint_number != None,
            User.fingerprint_number != ''
        ).count()
        
        # Count all departments (only those with employees)
        from models import Department
        stats['total_departments'] = Department.query.count()
        
        # Add attendance statistics for today using AttendanceLog
        from models import AttendanceLog
        from datetime import date, datetime
        today = date.today()
        
        # Count employees present today using AttendanceLog (any log = present)
        from models import AttendanceLog
        from datetime import datetime
        
        # Get users who have ANY attendance log today (check-in OR check-out)
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today, datetime.max.time())
        
        present_users = db.session.query(AttendanceLog.user_id).join(User).filter(
            AttendanceLog.timestamp.between(start_datetime, end_datetime),
            User.fingerprint_number != None,
            User.fingerprint_number != '',
            User.status == 'active',
            User.role.notin_(['admin', 'product_owner'])
        ).distinct().count()
        
        stats['total_attendance_today'] = present_users
        
        # Count employees absent today (only those with fingerprint numbers)
        total_active_employees_with_fingerprint = User.query.filter(
            User.status == 'active', 
            User.role.notin_(['admin', 'product_owner']),
            User.fingerprint_number != None,
            User.fingerprint_number != ''
        ).count()
        
        stats['team_absent_today'] = total_active_employees_with_fingerprint - stats['total_attendance_today']
        
        # Calculate attendance rate
        if total_active_employees_with_fingerprint > 0:
            stats['attendance_rate'] = round((stats['total_attendance_today'] / total_active_employees_with_fingerprint) * 100, 1)
        else:
            stats['attendance_rate'] = 0
    
    elif user.role == 'director':
        # Director sees all company-wide stats (same as admin but view-only)
        stats['pending_leave_requests'] = LeaveRequest.query.filter_by(status='pending').count()
        
        # All pending permission requests
        stats['pending_permission_requests'] = PermissionRequest.query.filter_by(status='pending').count()
        
        # All approved leave requests
        stats['approved_leave_requests'] = LeaveRequest.query.filter_by(status='approved').count()
        
        # All approved permission requests
        stats['approved_permission_requests'] = PermissionRequest.query.filter_by(status='approved').count()
        
        # All rejected leave requests
        stats['rejected_leave_requests'] = LeaveRequest.query.filter_by(status='rejected').count()
        
        # All rejected permission requests
        stats['rejected_permission_requests'] = PermissionRequest.query.filter_by(status='rejected').count()
        
        # Count all employees (excluding admins and directors) with fingerprint numbers
        stats['total_employees'] = User.query.filter(
            User.status == 'active', 
            User.role.notin_(['admin', 'director']),
            User.fingerprint_number != None,
            User.fingerprint_number != ''
        ).count()
        
        # Count all departments
        from models import Department
        stats['total_departments'] = Department.query.count()
        
        # Add attendance statistics for today using AttendanceLog
        from models import AttendanceLog
        from datetime import date, datetime
        today = date.today()
        
        # Count employees present today using AttendanceLog (any log = present)
        from models import AttendanceLog
        from datetime import datetime
        
        # Get users who have ANY attendance log today (check-in OR check-out)
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today, datetime.max.time())
        
        present_users = db.session.query(AttendanceLog.user_id).join(User).filter(
            AttendanceLog.timestamp.between(start_datetime, end_datetime),
            User.fingerprint_number != None,
            User.fingerprint_number != '',
            User.status == 'active',
            User.role.notin_(['admin', 'director'])
        ).distinct().count()
        
        stats['total_attendance_today'] = present_users
        
        # Count employees absent today (only those with fingerprint numbers)
        total_active_employees_with_fingerprint = User.query.filter(
            User.status == 'active', 
            User.role.notin_(['admin', 'director']),
            User.fingerprint_number != None,
            User.fingerprint_number != ''
        ).count()
        
        stats['team_absent_today'] = total_active_employees_with_fingerprint - stats['total_attendance_today']
        
        # Calculate attendance rate
        if total_active_employees_with_fingerprint > 0:
            stats['attendance_rate'] = round((stats['total_attendance_today'] / total_active_employees_with_fingerprint) * 100, 1)
        else:
            stats['attendance_rate'] = 0
    
    # Add leave balance information for all roles
    from models import LeaveBalance, LeaveType
    from datetime import datetime
    
    current_year = datetime.now().year
    if user.role in ['admin', 'director']:
        # Admins and directors see all leave balances
        leave_balances = LeaveBalance.query.join(LeaveType).filter(
            LeaveBalance.year == current_year
        ).all()
    else:
        # Employees and managers see only their own balances
        leave_balances = LeaveBalance.query.join(LeaveType).filter(
            LeaveBalance.user_id == user.id,
            LeaveBalance.year == current_year
        ).all()
    
    stats['leave_balances'] = []
    for balance in leave_balances:
        stats['leave_balances'].append({
            'leave_type_name': balance.leave_type.name,
            'total_days': balance.total_days,
            'used_days': balance.used_days,
            'remaining_days': balance.remaining_days,
            'is_negative': balance.remaining_days < 0,
            'color': balance.leave_type.color
        })
    
    return stats

def connect_to_fingerprint_device(ip, port=4370):
    """
    Establishes connection with the fingerprint device
    Returns the connection object if successful, None otherwise
    """
    try:
        zk = ZK(ip, port=port, timeout=5)
        conn = zk.connect()
        return conn
    except Exception as e:
        logging.error(f"Error connecting to fingerprint device: {str(e)}")
        return None

def sync_users_from_device(ip="192.168.11.2", port=4370):
    """
    Fetches users from the fingerprint device and syncs them with the database
    Returns tuple (success: bool, message: str)
    """
    conn = None
    try:
        conn = connect_to_fingerprint_device(ip, port)
        if not conn:
            return False, "Could not connect to the device"

        # Get all users from the device
        device_users = conn.get_users()
        if not device_users:
            return False, "No users found on the device"

        # Process each user from the device
        for device_user in device_users:
            # Check if user already exists in database by fingerprint number
            user = User.query.filter_by(fingerprint_number=str(device_user.uid)).first()
            
            if user:
                # User already exists, skip updating their data
                logging.info(f"Existing user skipped: {user.first_name} (Fingerprint ID: {user.fingerprint_number})")
            else:
                # Create new user
                new_user = User(
                    first_name=device_user.name,
                    last_name="",  # Device might not provide last name
                    email=f"fp_{device_user.uid}@placeholder.com",  # Placeholder email
                    password_hash="",  # Will need to be set later
                    fingerprint_number=str(device_user.uid),
                    role='employee',  # Default role
                    status='active'
                )
                db.session.add(new_user)
                db.session.commit()
                logging.info(f"New user created: {new_user.first_name} (Fingerprint ID: {new_user.fingerprint_number})")

        db.session.commit()
        return True, f"Successfully synced {len(device_users)} users from the device"

    except Exception as e:
        db.session.rollback()
        error_msg = f"Error syncing users: {str(e)}"
        logging.error(error_msg)
        return False, error_msg
    
    finally:
        if conn:
            conn.disconnect()

def format_hours_minutes(hours):
    """Convert decimal hours to 'Xh Ym' format."""
    if hours is None or hours == 0:
        return "0h 0m"
    
    # Handle negative hours
    is_negative = hours < 0
    hours = abs(hours)
    
    # Extract hours and minutes
    whole_hours = int(hours)
    minutes = int((hours - whole_hours) * 60)
    
    # Format the result
    if whole_hours > 0 and minutes > 0:
        result = f"{whole_hours}h {minutes}m"
    elif whole_hours > 0:
        result = f"{whole_hours}h 0m"
    elif minutes > 0:
        result = f"0h {minutes}m"
    else:
        result = "0h 0m"
    
    # Add negative sign if needed
    if is_negative:
        result = f"-{result}"
    
    return result

def send_admin_email_notification(subject, message, request_type=None, request_id=None):
    """Send email notifications based on module-specific email lists for leave/permission requests."""
    try:
        # Get active SMTP configuration
        smtp_config = SMTPConfiguration.query.filter_by(is_active=True).first()
        if not smtp_config:
            logging.warning("No active SMTP configuration found. Email notification not sent.")
            return False
        
        # Determine which emails to send to based on request type
        recipient_emails = []
        
        if request_type == 'leave':
            if not smtp_config.notify_leave_requests:
                logging.info("Leave request notifications are disabled. Email not sent.")
                return False
            recipient_emails = smtp_config.get_leave_emails()
        elif request_type == 'permission':
            if not smtp_config.notify_permission_requests:
                logging.info("Permission request notifications are disabled. Email not sent.")
                return False
            recipient_emails = smtp_config.get_permission_emails()
        else:
            # For general admin notifications
            recipient_emails = smtp_config.get_admin_emails()
        
        if not recipient_emails:
            logging.warning(f"No recipient emails found for {request_type} notifications. Email not sent.")
            return False
        
        # Import email libraries
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Connect to SMTP server
        if smtp_config.use_ssl:
            server = smtplib.SMTP_SSL(smtp_config.smtp_server, smtp_config.smtp_port)
        else:
            server = smtplib.SMTP(smtp_config.smtp_server, smtp_config.smtp_port)
            if smtp_config.use_tls:
                server.starttls()
        
        try:
            server.login(smtp_config.smtp_username, smtp_config.smtp_password)
        except Exception as login_error:
            logging.error(f"SMTP login failed: {str(login_error)}")
            server.quit()
            return False
        
        # Send email to each recipient
        for recipient_email in recipient_emails:
            try:
                # Try to get the user's name if they exist in the system
                user = User.query.filter_by(email=recipient_email).first()
                recipient_name = user.get_full_name() if user else recipient_email.split('@')[0].title()
                
                msg = MIMEMultipart()
                msg['From'] = f"{smtp_config.sender_name} <{smtp_config.sender_email}>"
                msg['To'] = recipient_email
                msg['Subject'] = subject
                
                # Create HTML email body
                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                            <h2 style="margin: 0; font-size: 24px;">
                                <span style="margin-right: 10px;">📧</span>
                                EverLastERP Notification
                            </h2>
                        </div>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea;">
                            <h3 style="color: #667eea; margin-top: 0;">Hello {recipient_name},</h3>
                            <p>{message}</p>
                            
                            {f'<p><strong>Request Type:</strong> {request_type.title()}</p>' if request_type else ''}
                            {f'<p><strong>Request ID:</strong> #{request_id}</p>' if request_id else ''}
                            
                            <div style="margin: 20px 0; padding: 15px; background: #e3f2fd; border-radius: 6px;">
                                <p style="margin: 0; font-size: 14px; color: #1565c0;">
                                    <strong>Action Required:</strong> Please log in to the EverLastERP system to review and process this request.
                                </p>
                            </div>
                        </div>
                        
                        <div style="margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 8px; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: #666;">
                                This is an automated message from EverLastERP System.<br>
                                Please do not reply to this email.
                            </p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                msg.attach(MIMEText(html_body, 'html'))
                server.send_message(msg)
                logging.info(f"Email notification sent to: {recipient_email}")
                
            except Exception as e:
                logging.error(f"Failed to send email to {recipient_email}: {str(e)}")
                continue
        
        server.quit()
        return True
        
    except Exception as e:
        logging.error(f"Failed to send admin email notifications: {str(e)}")
        return False
