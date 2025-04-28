from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import User, Department, LeaveRequest, PermissionRequest
from helpers import get_dashboard_stats, role_required

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard route that redirects based on user role"""
    if current_user.role == 'employee':
        return redirect(url_for('dashboard.employee'))
    elif current_user.role == 'manager':
        return redirect(url_for('dashboard.manager'))
    elif current_user.role == 'admin':
        return redirect(url_for('dashboard.admin'))
    elif current_user.role == 'director':
        return redirect(url_for('dashboard.director'))
    return redirect(url_for('dashboard.employee'))  # Fallback

@dashboard_bp.route('/employee')
@login_required
def employee():
    """Employee dashboard showing their requests"""
    stats = get_dashboard_stats(current_user)
    
    # Get the user's leave and permission requests
    leave_requests = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    permission_requests = PermissionRequest.query.filter_by(user_id=current_user.id).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    
    return render_template('dashboard/employee.html', 
                           title='Employee Dashboard',
                           stats=stats,
                           leave_requests=leave_requests,
                           permission_requests=permission_requests)

@dashboard_bp.route('/manager')
@login_required
@role_required('manager', 'admin', 'director')
def manager():
    """Manager dashboard showing department employee requests"""
    stats = get_dashboard_stats(current_user)
    
    # Get employees from the manager's department
    if current_user.managed_department:
        department_id = current_user.managed_department[0].id if current_user.managed_department else None
        employees = User.query.filter_by(department_id=department_id).all() if department_id else []
        
        # Get pending requests that need manager approval
        pending_leave_requests = []
        pending_permission_requests = []
        
        for employee in employees:
            # Get leave requests needing manager approval
            leave_requests = LeaveRequest.query.filter_by(
                user_id=employee.id,
                status='pending',
                manager_approved=False
            ).order_by(LeaveRequest.created_at.desc()).all()
            
            # Get permission requests needing manager approval
            permission_requests = PermissionRequest.query.filter_by(
                user_id=employee.id,
                status='pending',
                manager_approved=False
            ).order_by(PermissionRequest.created_at.desc()).all()
            
            pending_leave_requests.extend(leave_requests)
            pending_permission_requests.extend(permission_requests)
    else:
        employees = []
        pending_leave_requests = []
        pending_permission_requests = []
    
    return render_template('dashboard/manager.html',
                          title='Manager Dashboard',
                          stats=stats,
                          employees=employees,
                          pending_leave_requests=pending_leave_requests[:5],
                          pending_permission_requests=pending_permission_requests[:5])

@dashboard_bp.route('/admin')
@login_required
@role_required('admin')
def admin():
    """Admin dashboard showing all company data and analytics"""
    stats = get_dashboard_stats(current_user)
    
    # Get pending requests that need admin approval
    pending_leave_requests = LeaveRequest.query.filter_by(
        status='pending',
        manager_approved=True,
        admin_approved=False
    ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    
    pending_permission_requests = PermissionRequest.query.filter_by(
        status='pending',
        manager_approved=True,
        director_approved=True,
        admin_approved=False
    ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    
    # Get recent activity
    recent_leaves = LeaveRequest.query.order_by(LeaveRequest.updated_at.desc()).limit(5).all()
    recent_permissions = PermissionRequest.query.order_by(PermissionRequest.updated_at.desc()).limit(5).all()
    
    # Get all users for the admin view (including active and inactive)
    all_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    
    # Get department data for analytics
    departments = Department.query.all()
    department_data = []
    
    for dept in departments:
        dept_employees = User.query.filter_by(department_id=dept.id).count()
        dept_leaves = LeaveRequest.query.join(User).filter(
            User.department_id == dept.id,
            LeaveRequest.status == 'approved'
        ).count()
        dept_permissions = PermissionRequest.query.join(User).filter(
            User.department_id == dept.id,
            PermissionRequest.status == 'approved'
        ).count()
        
        department_data.append({
            'name': dept.department_name,
            'employees': dept_employees,
            'leaves': dept_leaves,
            'permissions': dept_permissions
        })
    
    return render_template('dashboard/admin.html',
                          title='Admin Dashboard',
                          stats=stats,
                          pending_leave_requests=pending_leave_requests,
                          pending_permission_requests=pending_permission_requests,
                          recent_leaves=recent_leaves,
                          recent_permissions=recent_permissions,
                          departments=departments,
                          department_data=department_data,
                          all_users=all_users)

@dashboard_bp.route('/director')
@login_required
@role_required('director')
def director():
    """Director dashboard focusing on permission requests approval"""
    stats = get_dashboard_stats(current_user)
    
    # Get pending permission requests that need director approval
    pending_permission_requests = PermissionRequest.query.filter_by(
        status='pending',
        manager_approved=True,
        director_approved=False
    ).order_by(PermissionRequest.created_at.desc()).limit(10).all()
    
    # Get recent activity
    recent_permissions = PermissionRequest.query.order_by(PermissionRequest.updated_at.desc()).limit(5).all()
    
    return render_template('dashboard/director.html',
                          title='Director Dashboard',
                          stats=stats,
                          pending_permission_requests=pending_permission_requests,
                          recent_permissions=recent_permissions)
