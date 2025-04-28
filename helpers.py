from datetime import datetime, date, timedelta
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user
from models import LeaveRequest, PermissionRequest, Notification, User
from app import db

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
    """Get the managers for a user (direct manager, admin, and director)."""
    managers = {
        'direct_manager': None,
        'admin_managers': [],
        'directors': []
    }
    
    if user.department and user.department.manager_id:
        managers['direct_manager'] = User.query.get(user.department.manager_id)
    
    # Get all admin users
    managers['admin_managers'] = User.query.filter_by(role='admin', status='active').all()
    
    # Get all directors
    managers['directors'] = User.query.filter_by(role='director', status='active').all()
    
    return managers

def get_employees_for_manager(manager_id):
    """Get all employees that report to a specific manager."""
    from models import Department
    
    # Find departments where this user is the manager
    departments = Department.query.filter_by(manager_id=manager_id).all()
    
    # Collect employees from these departments
    employees = []
    for dept in departments:
        dept_employees = User.query.filter_by(department_id=dept.id, status='active').all()
        employees.extend(dept_employees)
    
    return employees

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
                ~LeaveRequest.manager_approved
            ).count()
            
            stats['pending_permission_requests'] = PermissionRequest.query.filter(
                PermissionRequest.user_id.in_(employee_ids),
                PermissionRequest.status == 'pending',
                ~PermissionRequest.manager_approved
            ).count()
            
            stats['total_employees'] = len(employee_ids)
        
    elif user.role == 'director':
        # Director sees permission requests that need director approval
        stats['pending_permission_requests'] = PermissionRequest.query.filter(
            PermissionRequest.status == 'pending',
            PermissionRequest.manager_approved == True,
            PermissionRequest.director_approved == False
        ).count()
        
    elif user.role == 'admin':
        # Admin sees company-wide stats
        stats['pending_leave_requests'] = LeaveRequest.query.filter(
            LeaveRequest.status == 'pending',
            LeaveRequest.manager_approved == True,
            LeaveRequest.admin_approved == False
        ).count()
        
        stats['pending_permission_requests'] = PermissionRequest.query.filter(
            PermissionRequest.status == 'pending',
            PermissionRequest.manager_approved == True,
            PermissionRequest.director_approved == True,
            PermissionRequest.admin_approved == False
        ).count()
        
        stats['approved_leave_requests'] = LeaveRequest.query.filter_by(status='approved').count()
        stats['approved_permission_requests'] = PermissionRequest.query.filter_by(status='approved').count()
        stats['rejected_leave_requests'] = LeaveRequest.query.filter_by(status='rejected').count()
        stats['rejected_permission_requests'] = PermissionRequest.query.filter_by(status='rejected').count()
        stats['total_employees'] = User.query.filter(User.status == 'active', User.role != 'admin').count()
        stats['total_departments'] = db.session.query(db.func.count(db.distinct(User.department_id))).scalar()
    
    return stats
