from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import User, Department, LeaveRequest, PermissionRequest, Notification
from helpers import get_dashboard_stats, role_required
from forms import UserEditForm
from app import db
from datetime import datetime

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

@dashboard_bp.route('/users')
@login_required
@role_required('admin')
def users():
    """Admin page showing all users and allowing user management"""
    # Get all users, both active and inactive
    all_users = User.query.order_by(User.last_name).all()
    
    # Get all departments for filtering
    departments = Department.query.all()
    
    return render_template('dashboard/users.html',
                          title='User Management',
                          all_users=all_users,
                          departments=departments)

@dashboard_bp.route('/users/toggle_status/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def toggle_user_status(user_id):
    """Toggle a user's active/inactive status"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow deactivating yourself
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('dashboard.users'))
    
    # Toggle status
    user.status = 'inactive' if user.status == 'active' else 'active'
    user.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    status_text = 'activated' if user.status == 'active' else 'deactivated'
    flash(f'User {user.first_name} {user.last_name} has been {status_text}.', 'success')
    
    return redirect(url_for('dashboard.users'))

@dashboard_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_member(user_id):
    """Delete a user from the system"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('dashboard.users'))
    
    # Store user info for the flash message
    user_name = f"{user.first_name} {user.last_name}"
    
    try:
        # Delete user
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user_name} has been deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.users'))

@dashboard_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_user(user_id):
    """Edit user information"""
    user = User.query.get_or_404(user_id)
    
    # Get all departments for the department dropdown
    departments = Department.query.all()
    
    # Create form and populate with user data
    form = UserEditForm(obj=user)
    
    # Update department choices
    department_choices = [(0, 'No Department')] + [(d.id, d.department_name) for d in departments]
    form.department_id.choices = department_choices
    
    if form.validate_on_submit():
        # Update user data
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data
        user.role = form.role.data
        user.status = form.status.data
        
        # Handle department selection
        if form.department_id.data == 0:
            user.department_id = None
        else:
            user.department_id = form.department_id.data
            
        user.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
            flash(f'User {user.first_name} {user.last_name} has been updated successfully.', 'success')
            return redirect(url_for('dashboard.users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')
            
    return render_template('dashboard/edit_user.html',
                          title='Edit User',
                          form=form,
                          user=user)

@dashboard_bp.route('/members')
@login_required
def members():
    """Page showing all active members in the system"""
    # Get all active users ordered by last name
    active_users = User.query.filter_by(status='active').order_by(User.last_name, User.first_name).all()
    
    # Get all departments for filtering
    departments = Department.query.all()
    
    return render_template('dashboard/members.html',
                          title='Company Members',
                          active_users=active_users,
                          departments=departments)

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
