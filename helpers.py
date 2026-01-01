from datetime import datetime, date, timedelta
from functools import wraps
from flask import flash, redirect, url_for, abort, request, current_app
from flask_login import current_user
from models import LeaveRequest, PermissionRequest, User, SMTPConfiguration, EmailTemplate, Ticket, TicketCategory, TicketDepartmentMapping, TicketComment, TicketStatusHistory, TicketEmailTemplate, Department, ActivityLog
from extensions import db
from zk import ZK, const
import logging
import re

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
    """Decorator that checks if the current user is an admin or technical support."""
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
    
    # Get all admin and technical support users
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
    
    # Special case for admin and technical support users - they should see all employees
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
        
        # Add employee-specific attendance stats for today
        from models import AttendanceLog
        from datetime import date, datetime
        today = date.today()
        
        # Check if employee is present today using AttendanceLog (more reliable for real-time data)
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today, datetime.max.time())
        
        # Check if employee has ANY attendance log today (check-in OR check-out)
        has_attendance_log = AttendanceLog.query.filter(
            AttendanceLog.user_id == user.id,
            AttendanceLog.timestamp.between(start_datetime, end_datetime)
        ).first() is not None
        
        if has_attendance_log:
            stats['present_today'] = 1
            stats['absent_today'] = 0
            # Also set team_present_today and team_absent_today for consistency
            stats['team_present_today'] = 1
            stats['team_absent_today'] = 0
        else:
            stats['present_today'] = 0
            stats['absent_today'] = 1
            # Also set team_present_today and team_absent_today for consistency
            stats['team_present_today'] = 0
            stats['team_absent_today'] = 1
        
        # Get department information
        if user.department:
            stats['department_name'] = user.department.department_name
            # Count employees in the same department
            stats['total_employees'] = User.query.filter_by(
                department_id=user.department_id,
                status='active'
            ).count()
        else:
            stats['department_name'] = None
            stats['total_employees'] = 0
        
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
            from models import DailyAttendance, AttendanceLog
            from datetime import date, datetime
            today = date.today()
            
            # Filter to only active employees for counts
            active_employee_ids = [emp.id for emp in employees if emp.status == 'active']
            
            # Count team members present today using AttendanceLog (more reliable for real-time data)
            # Check for any attendance log today (check-in OR check-out)
            start_datetime = datetime.combine(today, datetime.min.time())
            end_datetime = datetime.combine(today, datetime.max.time())
            
            # Get users who have ANY attendance log today
            present_user_ids = db.session.query(AttendanceLog.user_id).filter(
                AttendanceLog.timestamp.between(start_datetime, end_datetime),
                AttendanceLog.user_id.in_(active_employee_ids)
            ).distinct().all()
            
            # Convert to list of IDs
            present_user_ids_list = [user_id[0] for user_id in present_user_ids]
            stats['team_present_today'] = len(present_user_ids_list)
            
            # Count team members absent today (only active employees)
            stats['team_absent_today'] = len(active_employee_ids) - stats['team_present_today']
            
            # Count only active employees
            stats['total_employees'] = len(active_employee_ids)
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
        
        # Count all employees with fingerprint numbers (including all roles)
        stats['total_employees'] = User.query.filter(
            User.status == 'active', 
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
        stats['team_present_today'] = present_users  # Also set for consistency
        
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
        stats['team_present_today'] = present_users  # Also set for consistency
        
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
                # User already exists - only update email if it's a placeholder
                if user.email and ('placeholder' in user.email.lower() or 
                                  user.email.startswith('fp_user_') or 
                                  (user.email.startswith('fp_') and '@placeholder' in user.email) or
                                  '@company.com' in user.email.lower()):
                    # Generate proper email from user's name
                    name_parts = (user.first_name + ' ' + (user.last_name or '')).strip().split()
                    if len(name_parts) >= 2:
                        first_name = name_parts[0].lower()
                        last_name = name_parts[-1].lower()
                        base_email = f"{first_name}.{last_name}@everlastwellness.com"
                    else:
                        name_lower = name_parts[0].lower() if name_parts else "user"
                        base_email = f"{name_lower}.{name_lower}@everlastwellness.com"
                    
                    # Ensure email uniqueness
                    email = base_email
                    counter = 1
                    while User.query.filter_by(email=email).filter(User.id != user.id).first():
                        if len(name_parts) >= 2:
                            email = f"{first_name}.{last_name}{counter}@everlastwellness.com"
                        else:
                            email = f"{name_lower}{counter}@everlastwellness.com"
                        counter += 1
                    
                    old_email = user.email
                    user.email = email
                    logging.info(f"Updated placeholder email for existing user: {user.first_name} (Old: {old_email}, New: {email})")
                else:
                    # User has proper email, keep it
                    logging.info(f"Existing user skipped: {user.first_name} (Fingerprint ID: {user.fingerprint_number}, Email: {user.email})")
            else:
                # Generate proper email from user's name
                # Format: firstname.lastname@everlastwellness.com
                name_parts = device_user.name.strip().split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0].lower()
                    last_name = name_parts[-1].lower()
                    base_email = f"{first_name}.{last_name}@everlastwellness.com"
                else:
                    # If only one name, use it for both
                    name_lower = name_parts[0].lower() if name_parts else "user"
                    base_email = f"{name_lower}.{name_lower}@everlastwellness.com"
                
                # Ensure email uniqueness
                email = base_email
                counter = 1
                while User.query.filter_by(email=email).first():
                    if len(name_parts) >= 2:
                        email = f"{first_name}.{last_name}{counter}@everlastwellness.com"
                    else:
                        email = f"{name_lower}{counter}@everlastwellness.com"
                    counter += 1
                
                # Create new user
                new_user = User(
                    first_name=device_user.name,
                    last_name="",  # Device might not provide last name
                    email=email,  # Proper email based on name
                    password_hash="",  # Will need to be set later
                    fingerprint_number=str(device_user.uid),
                    role='employee',  # Default role
                    status='active'
                )
                db.session.add(new_user)
                db.session.commit()
                logging.info(f"New user created: {new_user.first_name} (Fingerprint ID: {new_user.fingerprint_number}, Email: {email})")

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

def get_fingerprint_filter():
    """
    Returns filter conditions for users with fingerprint numbers.
    Returns a tuple that can be unpacked with * in query filters.
    """
    from models import User
    return (
        User.fingerprint_number != None,
        User.fingerprint_number != ''
    )

def has_valid_fingerprint(user):
    """
    Check if a user has a valid fingerprint number.
    
    Args:
        user: User object to check
        
    Returns:
        bool: True if user has a valid fingerprint number, False otherwise
    """
    if not user:
        return False
    return user.fingerprint_number is not None and user.fingerprint_number != ''

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
                                Everlast HR System Notification
                            </h2>
                        </div>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea;">
                            <h3 style="color: #667eea; margin-top: 0;">Hello {recipient_name},</h3>
                            <p>{message}</p>
                            
                            {f'<p><strong>Request Type:</strong> {request_type.title()}</p>' if request_type else ''}
                            
                            <div style="margin: 20px 0; padding: 15px; background: #e3f2fd; border-radius: 6px;">
                                <p style="margin: 0; font-size: 14px; color: #1565c0;">
                                    <strong>Action Required:</strong> Please log in to the Everlast HR System to review and process this request.
                                </p>
                            </div>
                        </div>
                        
                        <div style="margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 8px; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: #666;">
                                This is an automated message from Everlast HR System.<br>
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


def get_email_template(template_type):
    """Get active email template by type"""
    try:
        template = EmailTemplate.query.filter_by(
            template_type=template_type,
            is_active=True
        ).first()
        if not template:
            logging.warning(f"Email template '{template_type}' not found or not active")
        return template
    except Exception as e:
        logging.error(f"Error retrieving email template {template_type}: {str(e)}")
        return None


def render_email_template(template, context_dict):
    """Render email template by replacing placeholders with context values"""
    if not template:
        logging.warning("Cannot render email template: template is None")
        return None, None
    
    try:
        logging.info(f"Rendering email template '{template.template_name}' with {len(context_dict)} context variables")
        
        # Replace placeholders in subject
        subject = template.subject
        for key, value in context_dict.items():
            placeholder = f"{{{key}}}"
            subject = subject.replace(placeholder, str(value) if value is not None else "")
        
        # Replace placeholders in body
        body = template.body_html
        if not body:
            logging.error(f"Email template '{template.template_name}' has empty body_html")
            return None, None
            
        for key, value in context_dict.items():
            placeholder = f"{{{key}}}"
            body = body.replace(placeholder, str(value) if value is not None else "")
        
        # Add footer if exists
        if template.footer:
            footer = template.footer
            for key, value in context_dict.items():
                placeholder = f"{{{key}}}"
                footer = footer.replace(placeholder, str(value) if value is not None else "")
            body += f"\n<br><br>{footer}"
        
        # Add signature if exists
        if template.signature:
            signature = template.signature
            for key, value in context_dict.items():
                placeholder = f"{{{key}}}"
                signature = signature.replace(placeholder, str(value) if value is not None else "")
            body += f"\n<br><br>{signature}"
        
        logging.info(f"Email template rendered successfully. Subject length: {len(subject)}, Body length: {len(body)}")
        return subject, body
    except Exception as e:
        logging.error(f"Error rendering email template '{template.template_name if template else 'Unknown'}': {str(e)}", exc_info=True)
        return None, None


def send_email_to_user(user, subject, html_body):
    """Send email to a specific user"""
    if not user:
        logging.warning(f"Cannot send email: user is None")
        return False
    
    if not user.email:
        logging.warning(f"Cannot send email to user {user.id} ({user.get_full_name()}): email address is missing")
        return False
    
    try:
        smtp_config = SMTPConfiguration.query.filter_by(is_active=True).first()
        if not smtp_config:
            logging.warning("No active SMTP configuration found. Email not sent.")
            return False
        
        logging.info(f"=== EMAIL SENDING PROCESS ===")
        logging.info(f"Recipient: {user.get_full_name()} ({user.email})")
        logging.info(f"Subject: {subject[:100]}")
        logging.info(f"SMTP Server: {smtp_config.smtp_server}:{smtp_config.smtp_port}")
        logging.info(f"SMTP Username: {smtp_config.smtp_username}")
        logging.info(f"Use SSL: {smtp_config.use_ssl}, Use TLS: {smtp_config.use_tls}")
        logging.info(f"Attempting to send email...")
        
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Connect to SMTP server with timeout
        try:
            if smtp_config.use_ssl:
                server = smtplib.SMTP_SSL(smtp_config.smtp_server, smtp_config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_config.smtp_server, smtp_config.smtp_port, timeout=30)
                if smtp_config.use_tls:
                    server.starttls()
        except Exception as conn_error:
            logging.error(f"SMTP connection failed to {smtp_config.smtp_server}:{smtp_config.smtp_port}: {str(conn_error)}", exc_info=True)
            return False
        
        try:
            logging.info(f"Attempting SMTP login with username: {smtp_config.smtp_username}")
            server.login(smtp_config.smtp_username, smtp_config.smtp_password)
            logging.info(f"✅ SMTP login successful for {smtp_config.smtp_username}")
        except Exception as login_error:
            logging.error(f"❌ SMTP login FAILED for {smtp_config.smtp_username}")
            logging.error(f"   Error: {str(login_error)}")
            logging.error(f"   This usually means the SMTP password is incorrect or has expired.")
            logging.error(f"   Please update the SMTP password in Settings > SMTP Configuration")
            try:
                server.quit()
            except:
                pass
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{smtp_config.sender_name} <{smtp_config.sender_email}>"
            msg['To'] = user.email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(html_body, 'html'))
            server.send_message(msg)
            logging.info(f"Email sent successfully to {user.email}: {subject}")
            return True
        except Exception as send_error:
            logging.error(f"Failed to send email to {user.email}: {str(send_error)}", exc_info=True)
            return False
        finally:
            try:
                server.quit()
            except Exception as quit_error:
                logging.warning(f"Error closing SMTP connection: {str(quit_error)}")
        
    except Exception as e:
        logging.error(f"Failed to send email to {user.email}: {str(e)}", exc_info=True)
        return False


def send_email_to_address(email_address, subject, html_body, recipient_name=None):
    """Send email to a specific email address"""
    if not email_address:
        logging.warning(f"Cannot send email: email address is None or empty")
        return False
    
    try:
        smtp_config = SMTPConfiguration.query.filter_by(is_active=True).first()
        if not smtp_config:
            logging.warning("No active SMTP configuration found. Email not sent.")
            return False
        
        logging.info(f"=== EMAIL SENDING PROCESS ===")
        logging.info(f"Recipient: {recipient_name or email_address} ({email_address})")
        logging.info(f"Subject: {subject[:100]}")
        logging.info(f"SMTP Server: {smtp_config.smtp_server}:{smtp_config.smtp_port}")
        logging.info(f"SMTP Username: {smtp_config.smtp_username}")
        logging.info(f"Use SSL: {smtp_config.use_ssl}, Use TLS: {smtp_config.use_tls}")
        logging.info(f"Attempting to send email...")
        
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Connect to SMTP server with timeout
        try:
            if smtp_config.use_ssl:
                server = smtplib.SMTP_SSL(smtp_config.smtp_server, smtp_config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_config.smtp_server, smtp_config.smtp_port, timeout=30)
                if smtp_config.use_tls:
                    server.starttls()
        except Exception as conn_error:
            logging.error(f"SMTP connection failed to {smtp_config.smtp_server}:{smtp_config.smtp_port}: {str(conn_error)}", exc_info=True)
            return False
        
        try:
            logging.info(f"Attempting SMTP login with username: {smtp_config.smtp_username}")
            server.login(smtp_config.smtp_username, smtp_config.smtp_password)
            logging.info(f"✅ SMTP login successful for {smtp_config.smtp_username}")
        except Exception as login_error:
            logging.error(f"❌ SMTP login FAILED for {smtp_config.smtp_username}")
            logging.error(f"   Error: {str(login_error)}")
            logging.error(f"   This usually means the SMTP password is incorrect or has expired.")
            logging.error(f"   Please update the SMTP password in Settings > SMTP Configuration")
            try:
                server.quit()
            except:
                pass
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{smtp_config.sender_name} <{smtp_config.sender_email}>"
            msg['To'] = email_address
            msg['Subject'] = subject
            
            msg.attach(MIMEText(html_body, 'html'))
            server.send_message(msg)
            logging.info(f"Email sent successfully to {email_address}: {subject}")
            return True
        except Exception as send_error:
            logging.error(f"Failed to send email to {email_address}: {str(send_error)}", exc_info=True)
            return False
        finally:
            try:
                server.quit()
            except Exception as quit_error:
                logging.warning(f"Error closing SMTP connection: {str(quit_error)}")
        
    except Exception as e:
        logging.error(f"Failed to send email to {email_address}: {str(e)}", exc_info=True)
        return False


def send_email_to_manager(employee, template_type, request_data):
    """Send email to employee's direct manager"""
    try:
        # Get employee's manager
        manager = None
        if employee.department and employee.department.manager_id:
            manager = User.query.get(employee.department.manager_id)
        
        # If no manager, fallback to admin
        if not manager:
            manager = User.query.filter(User.role.in_(['admin', 'product_owner'])).first()
        
        if not manager:
            logging.warning(f"No manager or admin found for employee {employee.id}")
            return False
        
        # Get template
        template = get_email_template(template_type)
        if not template:
            logging.warning(f"Email template {template_type} not found")
            return False
        
        # Prepare context
        context = {
            'employee_name': employee.get_full_name(),
            'manager_name': manager.get_full_name(),
            'request_type': request_data.get('request_type', 'Request'),
            'start_date': request_data.get('start_date', ''),
            'end_date': request_data.get('end_date', ''),
            'duration': request_data.get('duration', ''),
            'reason': request_data.get('reason', ''),
            'request_id': request_data.get('request_id', ''),
            'approval_link': request_data.get('approval_link', ''),
        }
        
        # Render template
        subject, html_body = render_email_template(template, context)
        if not subject or not html_body:
            logging.error(f"Failed to render email template {template_type}")
            return False
        
        # Send email
        return send_email_to_user(manager, subject, html_body)
        
    except Exception as e:
        logging.error(f"Error sending email to manager: {str(e)}")
        return False


def send_email_to_admin(employee, template_type, request_data):
    """Send email to admin users"""
    try:
        # Get template
        template = get_email_template(template_type)
        if not template:
            logging.warning(f"Email template {template_type} not found")
            return False
        
        # Get ALL admin users (admin and product_owner roles)
        admins = User.query.filter(
            User.role.in_(['admin', 'product_owner']),
            User.status == 'active'
        ).all()
        
        if not admins:
            logging.warning("No active admin users found")
            return False
        
        logging.info(f"Found {len(admins)} active admin/product_owner users to notify:")
        for admin in admins:
            logging.info(f"  - {admin.get_full_name()} ({admin.email}) - Role: {admin.role}")
        
        # Prepare context
        context = {
            'employee_name': employee.get_full_name(),
            'admin_name': 'Admin',
            'request_type': request_data.get('request_type', 'Request'),
            'start_date': request_data.get('start_date', ''),
            'end_date': request_data.get('end_date', ''),
            'duration': request_data.get('duration', ''),
            'reason': request_data.get('reason', ''),
            'comment': request_data.get('comment', ''),
            'manager_name': request_data.get('manager_name', ''),
            'request_id': request_data.get('request_id', ''),
            'approval_link': request_data.get('approval_link', ''),
        }
        
        # Render template
        subject, html_body = render_email_template(template, context)
        if not subject or not html_body:
            logging.error(f"Failed to render email template {template_type}")
            return False
        
        # Send to ALL admins
        logging.info(f"=== SENDING EMAIL TO ALL ADMIN USERS ===")
        logging.info(f"Template: {template_type}")
        logging.info(f"Employee: {employee.get_full_name()} ({employee.email})")
        logging.info(f"Total admins to notify: {len(admins)}")
        
        success_count = 0
        failed_count = 0
        
        for admin in admins:
            # Personalize for each admin
            context['admin_name'] = admin.get_full_name()
            subject_personalized, html_body_personalized = render_email_template(template, context)
            
            logging.info(f"Attempting to send email to admin: {admin.get_full_name()} ({admin.email}) - Role: {admin.role}")
            
            if send_email_to_user(admin, subject_personalized, html_body_personalized):
                success_count += 1
                logging.info(f"✅ Email sent successfully to {admin.get_full_name()} ({admin.email})")
            else:
                failed_count += 1
                logging.error(f"❌ Failed to send email to {admin.get_full_name()} ({admin.email})")
        
        logging.info(f"=== EMAIL SENDING SUMMARY ===")
        logging.info(f"Total admins: {len(admins)}")
        logging.info(f"Successfully sent: {success_count}")
        logging.info(f"Failed: {failed_count}")
        
        return success_count > 0
        
    except Exception as e:
        logging.error(f"Error sending email to admin: {str(e)}")
        return False


def send_email_to_employee(employee, template_type, request_data):
    """Send email to employee"""
    try:
        # Check if employee has email
        if not employee or not employee.email:
            logging.warning(f"Cannot send email to employee {employee.id if employee else 'None'}: no email address")
            return False
        
        # Get template
        logging.info(f"Retrieving email template '{template_type}' for employee {employee.id}")
        template = get_email_template(template_type)
        if not template:
            logging.error(f"Email template '{template_type}' not found or not active. Cannot send email to {employee.email}")
            return False
        
        logging.info(f"Email template '{template_type}' found: {template.template_name} (active: {template.is_active})")
        
        # Prepare context
        context = {
            'employee_name': employee.get_full_name(),
            'request_type': request_data.get('request_type', 'Request'),
            'start_date': request_data.get('start_date', ''),
            'end_date': request_data.get('end_date', ''),
            'duration': request_data.get('duration', ''),
            'reason': request_data.get('reason', ''),
            'comment': request_data.get('comment', ''),
            'status': request_data.get('status', ''),
            'request_id': request_data.get('request_id', ''),
            'manager_name': request_data.get('manager_name', ''),
            'admin_name': request_data.get('admin_name', ''),
            'submission_date': request_data.get('submission_date', ''),
            'submission_time': request_data.get('submission_time', ''),
        }
        
        # Render template
        logging.info(f"Rendering email template '{template_type}' for employee {employee.id} ({employee.get_full_name()})")
        subject, html_body = render_email_template(template, context)
        if not subject or not html_body:
            logging.error(f"Failed to render email template {template_type}: subject={subject is not None}, body={html_body is not None}")
            return False
        
        logging.info(f"Email template rendered. Subject: {subject[:50]}..., Body length: {len(html_body)} chars")
        
        # Send email
        return send_email_to_user(employee, subject, html_body)
        
    except Exception as e:
        logging.error(f"Error sending email to employee: {str(e)}", exc_info=True)
        return False


# ============================================================================
# TICKETING SYSTEM HELPER FUNCTIONS
# ============================================================================

def get_tickets_for_user(user, show_own_only=False):
    """Returns tickets based on user role
    
    Args:
        user: The user object
        show_own_only: If True, always return only the user's own tickets (for "My Tickets" page)
                      If False, return tickets based on role (for inbox/manager views)
    """
    if not user or not user.is_authenticated:
        return []
    
    # If show_own_only is True, always return user's own tickets
    if show_own_only:
        return Ticket.query.filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).all()
    
    if user.role == 'product_owner':
        # Technical Support sees all tickets
        return Ticket.query.order_by(Ticket.created_at.desc()).all()
    elif user.role in ['admin', 'director']:
        # Admin/Director sees all tickets (same as Technical Support for now)
        return Ticket.query.order_by(Ticket.created_at.desc()).all()
    elif user.department_id:
        # Check if user's department is in ticket department mappings (IT/Web)
        department_ids = TicketDepartmentMapping.query.with_entities(
            TicketDepartmentMapping.department_id
        ).distinct().all()
        department_ids = [d[0] for d in department_ids]
        
        if user.department_id in department_ids:
            # IT/Web department users see all tickets assigned to their department
            category_ids = TicketDepartmentMapping.query.filter_by(
                department_id=user.department_id
            ).with_entities(TicketDepartmentMapping.category_id).distinct().all()
            category_ids = [c[0] for c in category_ids]
            
            if category_ids:
                return Ticket.query.filter(
                    Ticket.category_id.in_(category_ids)
                ).order_by(Ticket.created_at.desc()).all()
    
    # Regular employees see only their own tickets
    return Ticket.query.filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).all()


def get_department_tickets(department_id):
    """Returns tickets for a specific department (IT/Web)"""
    if not department_id:
        return []
    
    category_ids = TicketDepartmentMapping.query.filter_by(
        department_id=department_id
    ).with_entities(TicketDepartmentMapping.category_id).distinct().all()
    category_ids = [c[0] for c in category_ids]
    
    if not category_ids:
        return []
    
    return Ticket.query.filter(
        Ticket.category_id.in_(category_ids)
    ).order_by(Ticket.created_at.desc()).all()


def route_ticket_to_departments(ticket):
    """Routes ticket based on category mapping and returns list of department users"""
    if not ticket or not ticket.category_id:
        return []
    
    # Get departments assigned to this category
    mappings = TicketDepartmentMapping.query.filter_by(
        category_id=ticket.category_id
    ).all()
    
    if not mappings:
        return []
    
    # Get all users in those departments
    department_ids = [m.department_id for m in mappings]
    users = User.query.filter(
        User.department_id.in_(department_ids),
        User.status == 'active'
    ).all()
    
    return users


def can_user_view_ticket(user, ticket):
    """Check if user can view a specific ticket"""
    if not user or not ticket:
        return False
    
    if user.role == 'product_owner':
        return True
    
    if user.role in ['admin', 'director']:
        return True
    
    # Requester can always view their own ticket
    if ticket.user_id == user.id:
        return True
    
    # IT/Web department users can view tickets assigned to their department
    if user.department_id:
        department_ids = TicketDepartmentMapping.query.filter_by(
            category_id=ticket.category_id
        ).with_entities(TicketDepartmentMapping.department_id).all()
        department_ids = [d[0] for d in department_ids]
        
        if user.department_id in department_ids:
            return True
    
    return False


def can_user_reply_to_ticket(user, ticket):
    """Check if user can reply to a ticket"""
    if not can_user_view_ticket(user, ticket):
        return False
    
    # Technical Support, Admin, Director can always reply
    if user.role in ['product_owner', 'admin', 'director']:
        return True
    
    # IT/Web department users can reply
    if user.department_id:
        department_ids = TicketDepartmentMapping.query.filter_by(
            category_id=ticket.category_id
        ).with_entities(TicketDepartmentMapping.department_id).all()
        department_ids = [d[0] for d in department_ids]
        
        if user.department_id in department_ids:
            return True
    
    # Requester can reply to their own ticket
    if ticket.user_id == user.id:
        return True
    
    return False


def get_ticket_email_template(template_type):
    """Get active ticket email template by type"""
    try:
        template = TicketEmailTemplate.query.filter_by(
            template_type=template_type,
            is_active=True
        ).first()
        if not template:
            logging.warning(f"Ticket email template '{template_type}' not found or not active")
        return template
    except Exception as e:
        logging.error(f"Error retrieving ticket email template {template_type}: {str(e)}")
        return None


def render_ticket_email_template(template, context_dict):
    """Render ticket email template by replacing placeholders"""
    if not template:
        return None, None
    
    try:
        subject = template.subject
        for key, value in context_dict.items():
            placeholder = f"{{{key}}}"
            subject = subject.replace(placeholder, str(value) if value is not None else "")
        
        body = template.body_html
        for key, value in context_dict.items():
            placeholder = f"{{{key}}}"
            body = body.replace(placeholder, str(value) if value is not None else "")
        
        return subject, body
    except Exception as e:
        logging.error(f"Error rendering ticket email template: {str(e)}", exc_info=True)
        return None, None


def send_ticket_created_notification(ticket):
    """Send email notification when ticket is created - different emails for requester and department teams"""
    try:
        # Get assigned departments
        dept_users = route_ticket_to_departments(ticket)
        
        # Generate full URL for ticket
        try:
            with current_app.app_context():
                ticket_url = url_for('tickets.detail', id=ticket.id, _external=True)
        except:
            # Fallback if not in app context
            ticket_url = f"/tickets/{ticket.id}"
        
        success_count = 0
        
        # Send confirmation email to requester
        requester_template = get_ticket_email_template('ticket_created_requester')
        if requester_template:
            requester_context = {
                'ticket_id': ticket.id,
                'ticket_title': ticket.title,
                'requester_name': ticket.user.get_full_name(),
                'category_name': ticket.category.name if ticket.category else 'Uncategorized',
                'priority': ticket.priority.title(),
                'status': 'Open',
                'created_at': ticket.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'ticket_url': ticket_url
            }
            
            subject, html_body = render_ticket_email_template(requester_template, requester_context)
            if subject and html_body:
                if send_email_to_user(ticket.user, subject, html_body):
                    success_count += 1
                    logging.info(f"Sent ticket confirmation email to requester: {ticket.user.email}")
        else:
            logging.warning("Ticket created requester email template not found")
        
        # Group users by department and send department-specific emails
        if not ticket.category_id:
            return success_count > 0
        
        # Get department mappings for this ticket's category
        mappings = TicketDepartmentMapping.query.filter_by(
            category_id=ticket.category_id
        ).all()
        
        if not mappings:
            return success_count > 0
        
        # Group users by department
        from collections import defaultdict
        dept_users_dict = defaultdict(list)
        for user in dept_users:
            if user.email and user.id != ticket.user_id:  # Don't send duplicate to requester
                dept_users_dict[user.department_id].append(user)
        
        # Send email to each department's email address
        dept_template = get_ticket_email_template('ticket_created_department')
        if dept_template:
            for mapping in mappings:
                department_id = mapping.department_id
                department = Department.query.get(department_id)
                
                if not department:
                    continue
                
                # Check if department has an email address
                if not department.email:
                    logging.warning(f"Department {department.department_name} does not have an email address configured. Skipping email notification.")
                    continue
                
                # Prepare context with all ticket details
                dept_context = {
                    'department_name': department.department_name,  # Department name (e.g., "IT", "Web")
                    'requester_name': ticket.user.get_full_name(),  # Employee who submitted ticket
                    'ticket_id': ticket.id,
                    'ticket_title': ticket.title,
                    'description': ticket.description,
                    'category_name': ticket.category.name if ticket.category else 'Uncategorized',
                    'priority': ticket.priority.title(),
                    'status': 'Open',
                    'created_at': ticket.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'ticket_url': ticket_url
                }
                
                # Render template once per department
                subject, html_body = render_ticket_email_template(dept_template, dept_context)
                if subject and html_body:
                    # Send to department email address
                    if send_email_to_address(department.email, subject, html_body, recipient_name=department.department_name):
                        success_count += 1
                        logging.info(f"Sent ticket alert email to {department.department_name} department email: {department.email}")
        else:
            logging.warning("Ticket created department email template not found")
        
        return success_count > 0
    except Exception as e:
        logging.error(f"Error sending ticket created notification: {str(e)}", exc_info=True)
        return False


def send_ticket_reply_notification(ticket, comment):
    """Send email notification when a reply is added"""
    try:
        template = get_ticket_email_template('ticket_reply')
        if not template:
            logging.warning("Ticket reply email template not found")
            return False
        
        # Get assigned departments
        dept_users = route_ticket_to_departments(ticket)
        
        # Generate full URL for ticket
        try:
            with current_app.app_context():
                ticket_url = url_for('tickets.detail', id=ticket.id, _external=True)
        except:
            ticket_url = f"/tickets/{ticket.id}"
        
        # Prepare context
        context = {
            'ticket_id': ticket.id,
            'ticket_title': ticket.title,
            'requester_name': ticket.user.get_full_name(),
            'commenter_name': comment.user.get_full_name() if comment.user else 'System',
            'comment_text': comment.comment_text,
            'is_internal': 'Yes' if comment.is_internal else 'No',
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'ticket_url': ticket_url
        }
        
        subject, html_body = render_ticket_email_template(template, context)
        if not subject or not html_body:
            return False
        
        success_count = 0
        
        # Send to requester (if not internal comment)
        if not comment.is_internal:
            if send_email_to_user(ticket.user, subject, html_body):
                success_count += 1
        
        # Send to department emails instead of individual users
        if ticket.category_id:
            mappings = TicketDepartmentMapping.query.filter_by(
                category_id=ticket.category_id
            ).all()
            
            for mapping in mappings:
                department = Department.query.get(mapping.department_id)
                if department and department.email:
                    if send_email_to_address(department.email, subject, html_body, recipient_name=department.department_name):
                        success_count += 1
                        logging.info(f"Sent ticket reply notification to {department.department_name} department email: {department.email}")
        
        return success_count > 0
    except Exception as e:
        logging.error(f"Error sending ticket reply notification: {str(e)}", exc_info=True)
        return False


def send_ticket_status_update_notification(ticket, old_status, new_status):
    """Send email notification when ticket status is updated"""
    try:
        template = get_ticket_email_template('ticket_status_update')
        if not template:
            logging.warning("Ticket status update email template not found")
            return False
        
        # Get assigned departments
        dept_users = route_ticket_to_departments(ticket)
        
        # Generate full URL for ticket
        try:
            with current_app.app_context():
                ticket_url = url_for('tickets.detail', id=ticket.id, _external=True)
        except:
            ticket_url = f"/tickets/{ticket.id}"
        
        # Prepare context
        context = {
            'ticket_id': ticket.id,
            'ticket_title': ticket.title,
            'requester_name': ticket.user.get_full_name(),
            'old_status': old_status.title().replace('_', ' ') if old_status else 'N/A',
            'new_status': new_status.title().replace('_', ' '),
            'updated_at': ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'ticket_url': ticket_url
        }
        
        subject, html_body = render_ticket_email_template(template, context)
        if not subject or not html_body:
            return False
        
        success_count = 0
        
        # Send to requester
        if send_email_to_user(ticket.user, subject, html_body):
            success_count += 1
        
        # Send to department emails instead of individual users
        if ticket.category_id:
            mappings = TicketDepartmentMapping.query.filter_by(
                category_id=ticket.category_id
            ).all()
            
            for mapping in mappings:
                department = Department.query.get(mapping.department_id)
                if department and department.email:
                    if send_email_to_address(department.email, subject, html_body, recipient_name=department.department_name):
                        success_count += 1
                        logging.info(f"Sent ticket status update notification to {department.department_name} department email: {department.email}")
        
        return success_count > 0
    except Exception as e:
        logging.error(f"Error sending ticket status update notification: {str(e)}", exc_info=True)
        return False


def send_ticket_resolved_notification(ticket):
    """Send final confirmation email when ticket is resolved or closed"""
    try:
        template_type = 'ticket_resolved' if ticket.status == 'resolved' else 'ticket_closed'
        template = get_ticket_email_template(template_type)
        if not template:
            logging.warning(f"Ticket {template_type} email template not found")
            return False
        
        # Generate full URL for ticket
        try:
            with current_app.app_context():
                ticket_url = url_for('tickets.detail', id=ticket.id, _external=True)
        except:
            ticket_url = f"/tickets/{ticket.id}"
        
        # Prepare context
        context = {
            'ticket_id': ticket.id,
            'ticket_title': ticket.title,
            'requester_name': ticket.user.get_full_name(),
            'status': ticket.status.title().replace('_', ' '),
            'resolved_at': ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'ticket_url': ticket_url
        }
        
        subject, html_body = render_ticket_email_template(template, context)
        if not subject or not html_body:
            return False
        
        # Send to requester only
        return send_email_to_user(ticket.user, subject, html_body)
    except Exception as e:
        logging.error(f"Error sending ticket resolved notification: {str(e)}", exc_info=True)
        return False


def log_activity(user, action, entity_type=None, entity_id=None, before_values=None, after_values=None, ip_address=None, description=None):
    """
    Log user activity to the activity log table.
    
    Args:
        user: User object or user_id (int) - the user performing the action
        action: str - action type (e.g., 'login', 'logout', 'edit_user', 'delete_user')
        entity_type: str - type of entity being acted upon (e.g., 'user', 'department')
        entity_id: int - ID of the entity being acted upon
        before_values: dict - dictionary of values before the change
        after_values: dict - dictionary of values after the change
        ip_address: str - IP address of the user
        description: str - optional description of the action
    
    Returns:
        ActivityLog object if successful, None if error
    """
    try:
        import json
        from flask import request
        
        # Get user_id if user object is passed
        user_id = user.id if hasattr(user, 'id') else (user if isinstance(user, int) else None)
        
        # Get IP address from request if not provided
        if ip_address is None:
            if request:
                # Check for real client IP behind proxy/load balancer
                # X-Forwarded-For can contain multiple IPs (client, proxy1, proxy2), take the first one
                forwarded_for = request.headers.get('X-Forwarded-For', '')
                if forwarded_for:
                    # Split by comma and take the first IP, strip whitespace
                    ip_address = forwarded_for.split(',')[0].strip()
                else:
                    # Fall back to X-Real-IP header
                    ip_address = request.headers.get('X-Real-IP') or request.remote_addr
            else:
                ip_address = None
        
        # Serialize before_values and after_values to JSON strings
        before_json = json.dumps(before_values) if before_values else None
        after_json = json.dumps(after_values) if after_values else None
        
        # Create activity log entry
        activity_log = ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_values=before_json,
            after_values=after_json,
            ip_address=ip_address,
            description=description,
            created_at=datetime.utcnow()
        )
        
        db.session.add(activity_log)
        db.session.commit()
        
        return activity_log
    except Exception as e:
        # Log error but don't break the main application flow
        logging.error(f"Error logging activity: {str(e)}", exc_info=True)
        db.session.rollback()
        return None
