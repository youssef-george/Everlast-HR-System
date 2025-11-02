from datetime import datetime, date, timedelta
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user
from models import LeaveRequest, PermissionRequest, Notification, User
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
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator that checks if the current user is an admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role != 'admin':
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

def create_notification(user_id, message, notification_type, reference_id=None, reference_type=None):
    """Create a notification for a user."""
    notification = Notification(
        user_id=user_id,
        message=message,
        notification_type=notification_type,
        reference_id=reference_id,
        reference_type=reference_type
    )
    db.session.add(notification)
    db.session.commit()
    return notification

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
    
    # Get all admin users
    all_admins = User.query.filter_by(role='admin', status='active').all()
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
    
    # Special case for admin users - they should see all employees
    if manager.role == 'admin':
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
        'general_manager_status': leave_request.general_manager_status,
        'manager_comment': leave_request.manager_comment,
        'admin_comment': leave_request.admin_comment,
        'general_manager_comment': leave_request.general_manager_comment
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
        'manager_status': permission_request.manager_status,
        'director_status': permission_request.director_status,
        'admin_status': permission_request.admin_status,
        'manager_comment': permission_request.manager_comment,
        'director_comment': permission_request.director_comment,
        'admin_comment': permission_request.admin_comment,
        'manager_updated_at': permission_request.manager_updated_at.strftime('%Y-%m-%d %H:%M:%S') if permission_request.manager_updated_at else None,
        'director_updated_at': permission_request.director_updated_at.strftime('%Y-%m-%d %H:%M:%S') if permission_request.director_updated_at else None,
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
        'total_departments': 0
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
                PermissionRequest.manager_status == 'pending'
            ).count()
            
            stats['total_employees'] = len(employee_ids)
        
    elif user.role == 'director':
        # Director sees permission requests that need director approval
        stats['pending_permission_requests'] = PermissionRequest.query.filter(
            PermissionRequest.status == 'pending',
            PermissionRequest.manager_status == 'approved',
            PermissionRequest.director_status == 'pending'
        ).count()
        
    elif user.role == 'admin':
        # Admin sees requests that need admin approval
        stats['pending_leave_requests'] = LeaveRequest.query.filter(
            LeaveRequest.status == 'pending',
            LeaveRequest.manager_status == 'approved',
            LeaveRequest.admin_status == 'pending'
        ).count()
        
        # Pending permission requests that need admin approval
        stats['pending_permission_requests'] = PermissionRequest.query.filter(
            PermissionRequest.status == 'pending',
            PermissionRequest.manager_status == 'approved',
            PermissionRequest.director_status == 'approved',
            PermissionRequest.admin_status == 'pending'
        ).count()
        
        # All approved leave requests
        stats['approved_leave_requests'] = LeaveRequest.query.filter_by(status='approved').count()
        
        # All approved permission requests
        stats['approved_permission_requests'] = PermissionRequest.query.filter_by(status='approved').count()
        
        # All rejected leave requests
        stats['rejected_leave_requests'] = LeaveRequest.query.filter_by(status='rejected').count()
        
        # All rejected permission requests
        stats['rejected_permission_requests'] = PermissionRequest.query.filter_by(status='rejected').count()
        
        # Count all employees
        stats['total_employees'] = User.query.filter(User.status == 'active', User.role != 'admin').count()
        
        # Count all departments
        stats['total_departments'] = db.session.query(db.func.count(db.distinct(User.department_id))).scalar()
    
    elif user.role == 'general_manager':
        # General Manager sees requests that need their approval
        stats['pending_leave_requests'] = LeaveRequest.query.filter(
            LeaveRequest.status == 'pending',
            LeaveRequest.manager_status == 'approved',
            LeaveRequest.admin_status == 'approved',
            LeaveRequest.general_manager_status == 'pending'
        ).count()
        
        # All approved leave requests
        stats['approved_leave_requests'] = LeaveRequest.query.filter_by(status='approved').count()
        
        # All rejected leave requests
        stats['rejected_leave_requests'] = LeaveRequest.query.filter_by(status='rejected').count()
        
        # Count all employees
        stats['total_employees'] = User.query.filter(User.status == 'active').count()
        
        # Count all departments
        stats['total_departments'] = db.session.query(db.func.count(db.distinct(User.department_id))).scalar()
    
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
