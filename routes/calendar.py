from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import LeaveRequest, PermissionRequest, User, Department
from helpers import role_required

calendar_bp = Blueprint('calendar', __name__, url_prefix='/calendar')

@calendar_bp.route('/')
@login_required
def index():
    """Show the calendar page"""
    return render_template('calendar/index.html', title='Calendar')

@calendar_bp.route('/events')
@login_required
def events():
    """API endpoint to get calendar events based on user role"""
    user_role = current_user.role
    start_date = datetime.today() - timedelta(days=30)  # Default: show from 30 days ago
    end_date = datetime.today() + timedelta(days=90)    # Default: show 90 days ahead
    
    events = []
    
    if user_role == 'employee':
        # Employees see only their own leaves and permissions
        user_id = current_user.id
        
        # Get leave requests for this employee
        leaves = LeaveRequest.query.filter_by(user_id=user_id).all()
        for leave in leaves:
            color = '#17a74a' if leave.status == 'approved' else '#dc3545' if leave.status == 'rejected' else '#ffc107'
            events.append({
                'id': f"leave_{leave.id}",
                'title': f"Leave: {leave.reason[:20]}{'...' if len(leave.reason) > 20 else ''}",
                'start': leave.start_date.isoformat(),
                'end': (leave.end_date + timedelta(days=1)).isoformat(),  # Add 1 day to make it inclusive
                'color': color,
                'url': f"/leave/view/{leave.id}",
                'status': leave.status,
                'type': 'leave'
            })
        
        # Get permission requests for this employee
        permissions = PermissionRequest.query.filter_by(user_id=user_id).all()
        for permission in permissions:
            color = '#17a74a' if permission.status == 'approved' else '#dc3545' if permission.status == 'rejected' else '#ffc107'
            events.append({
                'id': f"permission_{permission.id}",
                'title': f"Permission: {permission.reason[:20]}{'...' if len(permission.reason) > 20 else ''}",
                'start': permission.start_time.isoformat(),
                'end': permission.end_time.isoformat(),
                'color': color,
                'url': f"/permission/view/{permission.id}",
                'status': permission.status,
                'type': 'permission'
            })
    
    elif user_role == 'manager':
        # Use the improved helper function to get all employees this manager manages
        from helpers import get_employees_for_manager
        employees = get_employees_for_manager(current_user.id)
        employee_ids = [emp.id for emp in employees]
        
        if employee_ids:
            # Get leave requests for these employees
            leaves = LeaveRequest.query.filter(LeaveRequest.user_id.in_(employee_ids)).all()
            for leave in leaves:
                employee = User.query.get(leave.user_id)
                color = '#17a74a' if leave.status == 'approved' else '#dc3545' if leave.status == 'rejected' else '#ffc107'
                events.append({
                    'id': f"leave_{leave.id}",
                    'title': f"{employee.get_full_name()} - Leave",
                    'start': leave.start_date.isoformat(),
                    'end': (leave.end_date + timedelta(days=1)).isoformat(),
                    'color': color,
                    'url': f"/leave/view/{leave.id}",
                    'status': leave.status,
                    'type': 'leave'
                })
            
            # Get permission requests for these employees
            permissions = PermissionRequest.query.filter(PermissionRequest.user_id.in_(employee_ids)).all()
            for permission in permissions:
                employee = User.query.get(permission.user_id)
                color = '#17a74a' if permission.status == 'approved' else '#dc3545' if permission.status == 'rejected' else '#ffc107'
                events.append({
                    'id': f"permission_{permission.id}",
                    'title': f"{employee.get_full_name()} - Permission",
                    'start': permission.start_time.isoformat(),
                    'end': permission.end_time.isoformat(),
                    'color': color,
                    'url': f"/permission/view/{permission.id}",
                    'status': permission.status,
                    'type': 'permission'
                })
        
        # ALSO include the manager's own leave and permission requests
        manager_leaves = LeaveRequest.query.filter_by(user_id=current_user.id).all()
        for leave in manager_leaves:
            color = '#17a74a' if leave.status == 'approved' else '#dc3545' if leave.status == 'rejected' else '#ffc107'
            events.append({
                'id': f"leave_{leave.id}",
                'title': f"My Leave: {leave.reason[:20]}{'...' if len(leave.reason) > 20 else ''}",
                'start': leave.start_date.isoformat(),
                'end': (leave.end_date + timedelta(days=1)).isoformat(),
                'color': color,
                'url': f"/leave/view/{leave.id}",
                'status': leave.status,
                'type': 'leave'
            })
        
        manager_permissions = PermissionRequest.query.filter_by(user_id=current_user.id).all()
        for permission in manager_permissions:
            color = '#17a74a' if permission.status == 'approved' else '#dc3545' if permission.status == 'rejected' else '#ffc107'
            events.append({
                'id': f"permission_{permission.id}",
                'title': f"My Permission: {permission.reason[:20]}{'...' if len(permission.reason) > 20 else ''}",
                'start': permission.start_time.isoformat(),
                'end': permission.end_time.isoformat(),
                'color': color,
                'url': f"/permission/view/{permission.id}",
                'status': permission.status,
                'type': 'permission'
            })
    
    elif user_role in ['admin', 'director']:
        # Admins and directors see all company-wide leaves and permissions
        # but distinguish between their own and others' requests
        
        # First get all leave requests
        if user_role == 'admin' and current_user.managed_department:
            # If admin is assigned to specific departments, only show requests from those departments
            admin_dept_ids = [dept.id for dept in current_user.managed_department]
            leaves = LeaveRequest.query.join(User).filter(User.department_id.in_(admin_dept_ids)).all()
        else:
            # Otherwise show all requests
            leaves = LeaveRequest.query.all()
            
        for leave in leaves:
            employee = User.query.get(leave.user_id)
            color = '#17a74a' if leave.status == 'approved' else '#dc3545' if leave.status == 'rejected' else '#ffc107'
            department = employee.department.department_name if employee.department else 'No Department'
            
            # Highlight the admin/director's own requests differently
            if leave.user_id == current_user.id:
                events.append({
                    'id': f"leave_{leave.id}",
                    'title': f"My Leave: {leave.reason[:20]}{'...' if len(leave.reason) > 20 else ''}",
                    'start': leave.start_date.isoformat(),
                    'end': (leave.end_date + timedelta(days=1)).isoformat(),
                    'color': color,
                    'url': f"/leave/view/{leave.id}",
                    'status': leave.status,
                    'type': 'leave'
                })
            else:
                events.append({
                    'id': f"leave_{leave.id}",
                    'title': f"{employee.get_full_name()} ({department}) - Leave",
                    'start': leave.start_date.isoformat(),
                    'end': (leave.end_date + timedelta(days=1)).isoformat(),
                    'color': color,
                    'url': f"/leave/view/{leave.id}",
                    'status': leave.status,
                    'type': 'leave'
                })
        
        # Get all permission requests
        if user_role == 'admin' and current_user.managed_department:
            # If admin is assigned to specific departments, only show requests from those departments
            admin_dept_ids = [dept.id for dept in current_user.managed_department]
            permissions = PermissionRequest.query.join(User).filter(User.department_id.in_(admin_dept_ids)).all()
        else:
            # Otherwise show all requests
            permissions = PermissionRequest.query.all()
            
        for permission in permissions:
            employee = User.query.get(permission.user_id)
            color = '#17a74a' if permission.status == 'approved' else '#dc3545' if permission.status == 'rejected' else '#ffc107'
            department = employee.department.department_name if employee.department else 'No Department'
            
            # Highlight the admin/director's own requests differently
            if permission.user_id == current_user.id:
                events.append({
                    'id': f"permission_{permission.id}",
                    'title': f"My Permission: {permission.reason[:20]}{'...' if len(permission.reason) > 20 else ''}",
                    'start': permission.start_time.isoformat(),
                    'end': permission.end_time.isoformat(),
                    'color': color,
                    'url': f"/permission/view/{permission.id}",
                    'status': permission.status,
                    'type': 'permission'
                })
            else:
                events.append({
                    'id': f"permission_{permission.id}",
                    'title': f"{employee.get_full_name()} ({department}) - Permission",
                    'start': permission.start_time.isoformat(),
                    'end': permission.end_time.isoformat(),
                    'color': color,
                    'url': f"/permission/view/{permission.id}",
                    'status': permission.status,
                    'type': 'permission'
                })
    
    return jsonify(events)
