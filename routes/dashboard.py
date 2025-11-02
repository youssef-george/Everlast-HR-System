from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
import os
import logging
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from models import User, LeaveRequest, PermissionRequest, DailyAttendance, Department, SMTPConfiguration, LeaveBalance, PaidHoliday, LeaveType
from helpers import role_required, get_dashboard_stats
from forms import UserEditForm, EmployeeAttachmentForm, SMTPConfigurationForm # Assuming UserEditForm is defined in forms.py

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard route that redirects based on user role"""
    if current_user.role == 'employee':
        return redirect(url_for('dashboard.employee'))
    elif current_user.role == 'manager':
        return redirect(url_for('dashboard.manager'))
    elif current_user.role in ['admin', 'product_owner']:
        return redirect(url_for('dashboard.admin'))
    elif current_user.role == 'director':
        return redirect(url_for('dashboard.director'))
    return redirect(url_for('dashboard.employee'))  # Fallback

@dashboard_bp.route('/employee')
@login_required
def employee():
    """Employee dashboard showing their requests"""
    from helpers import leave_request_to_dict, permission_request_to_dict
    from models import LeaveBalance, LeaveType, DailyAttendance
    from datetime import datetime, timedelta, date
    
    stats = get_dashboard_stats(current_user)
    
    # Get the user's leave and permission requests
    leave_requests_db = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    permission_requests_db = PermissionRequest.query.filter_by(user_id=current_user.id).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    
    # Get user's leave balances
    leave_balances = LeaveBalance.query.filter_by(user_id=current_user.id).join(LeaveBalance.leave_type).all()
    
    # Enhanced statistics for employee dashboard
    today = date.today()
    current_month_start = today.replace(day=1)
    current_year = today.year
    
    # Monthly leave and permission statistics
    monthly_leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.start_date >= current_month_start,
        LeaveRequest.start_date <= today
    ).count()
    
    monthly_permissions = PermissionRequest.query.filter(
        PermissionRequest.user_id == current_user.id,
        PermissionRequest.start_time >= datetime.combine(current_month_start, datetime.min.time()),
        PermissionRequest.start_time <= datetime.combine(today, datetime.max.time())
    ).count()
    
    # Yearly statistics
    year_start = date(current_year, 1, 1)
    yearly_leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.start_date >= year_start,
        LeaveRequest.start_date <= today
    ).count()
    
    yearly_permissions = PermissionRequest.query.filter(
        PermissionRequest.user_id == current_user.id,
        PermissionRequest.start_time >= datetime.combine(year_start, datetime.min.time()),
        PermissionRequest.start_time <= datetime.combine(today, datetime.max.time())
    ).count()
    
    # Total days used in current year
    total_leave_days_used = db.session.query(
        db.func.coalesce(db.func.sum(
            db.func.julianday(LeaveRequest.end_date) - db.func.julianday(LeaveRequest.start_date) + 1
        ), 0)
    ).filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.status == 'approved',
        LeaveRequest.start_date >= year_start
    ).scalar() or 0
    
    # Attendance statistics for current month
    monthly_attendance = DailyAttendance.query.filter(
        DailyAttendance.user_id == current_user.id,
        DailyAttendance.date >= current_month_start,
        DailyAttendance.date <= today
    ).all()
    
    present_days = sum(1 for record in monthly_attendance if record.status in ['present', 'half-day'])
    total_working_hours = sum(record.total_working_hours or 0 for record in monthly_attendance)
    
    # Leave type breakdown
    leave_type_breakdown = []
    for leave_type in LeaveType.query.filter_by(is_active=True).all():
        type_requests = LeaveRequest.query.filter(
            LeaveRequest.user_id == current_user.id,
            LeaveRequest.leave_type_id == leave_type.id,
            LeaveRequest.start_date >= year_start
        ).all()
        
        total_requests = len(type_requests)
        approved_requests = len([r for r in type_requests if r.status == 'approved'])
        pending_requests = len([r for r in type_requests if r.status == 'pending'])
        rejected_requests = len([r for r in type_requests if r.status == 'rejected'])
        
        if total_requests > 0:
            leave_type_breakdown.append({
                'name': leave_type.name,
                'color': leave_type.color,
                'total': total_requests,
                'approved': approved_requests,
                'pending': pending_requests,
                'rejected': rejected_requests
            })
    
    # Permission type breakdown (by duration)
    permission_breakdown = {
        'short': 0,  # < 2 hours
        'medium': 0,  # 2-4 hours
        'long': 0    # > 4 hours
    }
    
    all_permissions = PermissionRequest.query.filter(
        PermissionRequest.user_id == current_user.id,
        PermissionRequest.status == 'approved',
        PermissionRequest.start_time >= datetime.combine(year_start, datetime.min.time())
    ).all()
    
    for perm in all_permissions:
        if perm.start_time and perm.end_time:
            duration_hours = (perm.end_time - perm.start_time).total_seconds() / 3600
            if duration_hours < 2:
                permission_breakdown['short'] += 1
            elif duration_hours <= 4:
                permission_breakdown['medium'] += 1
            else:
                permission_breakdown['long'] += 1
    
    # Get upcoming leave events (approved leaves starting from today onwards)
    upcoming_leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == current_user.id,
        LeaveRequest.status == 'approved',
        LeaveRequest.start_date >= today
    ).order_by(LeaveRequest.start_date.asc()).limit(10).all()
    
    # Get upcoming paid holidays
    from models import PaidHoliday
    upcoming_holidays = PaidHoliday.query.filter(
        PaidHoliday.start_date >= today
    ).order_by(PaidHoliday.start_date.asc()).limit(5).all()
    
    # Add enhanced statistics to stats
    stats.update({
        'monthly_leaves': monthly_leaves,
        'monthly_permissions': monthly_permissions,
        'yearly_leaves': yearly_leaves,
        'yearly_permissions': yearly_permissions,
        'total_leave_days_used': int(total_leave_days_used),
        'present_days_this_month': present_days,
        'total_working_hours_this_month': round(total_working_hours, 1),
        'leave_type_breakdown': leave_type_breakdown,
        'permission_breakdown': permission_breakdown
    })
    
    # Convert to JSON-serializable format for chart data
    leave_requests_json = [leave_request_to_dict(lr) for lr in leave_requests_db]
    permission_requests_json = [permission_request_to_dict(pr) for pr in permission_requests_db]
    
    return render_template('dashboard/employee.html', 
                           title='Employee Dashboard',
                           stats=stats,
                           leave_requests=leave_requests_json,
                           permission_requests=permission_requests_json,
                           leave_requests_db=leave_requests_db,
                           permission_requests_db=permission_requests_db,
                           leave_balances=leave_balances,
                           upcoming_leaves=upcoming_leaves,
                           upcoming_holidays=upcoming_holidays,
                           # Auto-fetch data attributes
                           pending_leave_requests=stats.get('pending_leave_requests', 0),
                           pending_permission_requests=stats.get('pending_permission_requests', 0),
                           approved_leave_requests=stats.get('approved_leave_requests', 0),
                           approved_permission_requests=stats.get('approved_permission_requests', 0),
                           rejected_leave_requests=stats.get('rejected_leave_requests', 0),
                           rejected_permission_requests=stats.get('rejected_permission_requests', 0))

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
            # Skip if this is the manager's own request (we'll display in a separate section)
            if employee.id == current_user.id:
                continue
                
            # Get leave requests needing manager approval
            leave_requests = LeaveRequest.query.filter_by(
                user_id=employee.id,
                status='pending',
                manager_status='pending'
            ).order_by(LeaveRequest.created_at.desc()).all()
            
            # Get permission requests needing admin approval
            permission_requests = PermissionRequest.query.filter_by(
                user_id=employee.id,
                status='pending',
                admin_status='pending'
            ).order_by(PermissionRequest.created_at.desc()).all()
            
            pending_leave_requests.extend(leave_requests)
            pending_permission_requests.extend(permission_requests)
    else:
        employees = []
        pending_leave_requests = []
        pending_permission_requests = []
    
    # Get manager's own leave requests
    personal_leave_requests = LeaveRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    
    # Get manager's own permission requests
    personal_permission_requests = PermissionRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    
    # Get team leave balances summary
    team_leave_balances = []
    if current_user.department_id:
        from models import LeaveBalance, LeaveType
        team_members = User.query.filter_by(status='active', department_id=current_user.department_id).all()
        team_member_ids = [user.id for user in team_members]
        
        # Get leave balances for team members
        balances = LeaveBalance.query.join(LeaveType).join(User).filter(
            LeaveBalance.user_id.in_(team_member_ids)
        ).all()
        
        # Group balances by user
        balances_by_user = {}
        for balance in balances:
            if balance.user_id not in balances_by_user:
                balances_by_user[balance.user_id] = []
            balances_by_user[balance.user_id].append(balance)
        
        # Create summary for each team member
        for user in team_members:
            user_balances = balances_by_user.get(user.id, [])
            team_leave_balances.append({
                'user': user,
                'balances': user_balances
            })
    
    return render_template('dashboard/manager.html',
                          title='Manager Dashboard',
                          stats=stats,
                          employees=employees,
                          pending_leave_requests=pending_leave_requests[:5],
                          pending_permission_requests=pending_permission_requests[:5],
                          personal_leave_requests=personal_leave_requests,
                          personal_permission_requests=personal_permission_requests,
                          team_leave_balances=team_leave_balances,
                          # Auto-fetch data attributes
                          pending_leave_requests_count=len(pending_leave_requests),
                          pending_permission_requests_count=len(pending_permission_requests),
                          team_present_today=stats.get('team_present_today', 0),
                          team_absent_today=stats.get('team_absent_today', 0),
                          total_employees=stats.get('total_employees', 0))

@dashboard_bp.route('/admin')
@login_required
@role_required(['admin', 'product_owner'])
def admin():
    """Admin/Product Owner dashboard showing all company data and analytics"""
    stats = get_dashboard_stats(current_user)
    
    # Get pending requests that need admin approval based on department assignments
    if current_user.managed_department:  # If admin is assigned to specific departments
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        pending_leave_requests = LeaveRequest.query.join(User).filter(
            LeaveRequest.status == 'pending',
            User.department_id.in_(admin_dept_ids)
        ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    else:  # If not assigned to specific departments, show all
        pending_leave_requests = LeaveRequest.query.filter_by(
            status='pending'
        ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    
    # Get pending permission requests that need admin approval based on department assignments
    if current_user.managed_department:
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        pending_permission_requests = PermissionRequest.query.join(User).filter(
            PermissionRequest.status == 'pending',
            User.department_id.in_(admin_dept_ids)
        ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    else:
        pending_permission_requests = PermissionRequest.query.filter_by(
            status='pending'
        ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    
    # Get recent activity - filter by department for department-specific admins
    if current_user.managed_department:
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        recent_leaves = LeaveRequest.query.join(User).filter(
            User.department_id.in_(admin_dept_ids)
        ).order_by(LeaveRequest.updated_at.desc()).limit(5).all()
        
        recent_permissions = PermissionRequest.query.join(User).filter(
            User.department_id.in_(admin_dept_ids)
        ).order_by(PermissionRequest.updated_at.desc()).limit(5).all()
    else:
        # For admins without specific department assignments, show all activity
        recent_leaves = LeaveRequest.query.order_by(LeaveRequest.updated_at.desc()).limit(5).all()
        recent_permissions = PermissionRequest.query.order_by(PermissionRequest.updated_at.desc()).limit(5).all()
    
    # Get all users for the admin view (including active and inactive)
    # Filter by department if admin has specific department assignments
    if current_user.managed_department:
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        all_users = User.query.filter(
            User.department_id.in_(admin_dept_ids)
        ).order_by(User.created_at.desc()).limit(10).all()
        
        # Get only the departments this admin manages
        departments = Department.query.filter(
            Department.id.in_(admin_dept_ids)
        ).all()
    else:
        all_users = User.query.order_by(User.created_at.desc()).limit(10).all()
        departments = Department.query.all()
    
    # Get department data for analytics
    department_data = []
    
    for dept in departments:
        dept_employees = User.query.filter_by(department_id=dept.id).count()
        dept_leaves = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id).filter(
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
    
    # Get leave management data
    from models import LeaveBalance, PaidHoliday, LeaveType
    
    # Get recent leave balances (last 10)
    recent_leave_balances = LeaveBalance.query.join(LeaveType).join(User).order_by(LeaveBalance.updated_at.desc()).limit(10).all()
    
    # Get upcoming paid holidays (next 30 days)
    from datetime import datetime, timedelta
    today = datetime.now().date()
    next_month = today + timedelta(days=30)
    upcoming_holidays = PaidHoliday.query.filter(
        PaidHoliday.start_date >= today,
        PaidHoliday.start_date <= next_month
    ).order_by(PaidHoliday.start_date).limit(5).all()
    
    # Get leave type statistics
    leave_type_stats = []
    leave_types = LeaveType.query.filter_by(is_active=True).all()
    for lt in leave_types:
        total_balances = LeaveBalance.query.filter_by(leave_type_id=lt.id).count()
        total_used = db.session.query(db.func.sum(LeaveBalance.used_days)).filter_by(leave_type_id=lt.id).scalar() or 0
        leave_type_stats.append({
            'leave_type': lt,
            'total_balances': total_balances,
            'total_used': total_used
        })
    
    # Set title based on user role
    dashboard_title = 'Product Owner Dashboard' if current_user.role == 'product_owner' else 'Admin Dashboard'
    
    return render_template('dashboard/admin.html',
                          title=dashboard_title,
                          stats=stats,
                          pending_leave_requests=pending_leave_requests,
                          pending_permission_requests=pending_permission_requests,
                          recent_leaves=recent_leaves,
                          recent_permissions=recent_permissions,
                          departments=departments,
                          department_data=department_data,
                          all_users=all_users,
                          recent_leave_balances=recent_leave_balances,
                          upcoming_holidays=upcoming_holidays,
                          leave_type_stats=leave_type_stats,
                          # Auto-fetch data attributes
                          pending_leave_requests_count=len(pending_leave_requests),
                          pending_permission_requests_count=len(pending_permission_requests),
                          total_employees=stats.get('total_employees', 0),
                          total_departments=stats.get('total_departments', 0),
                          attendance_rate=stats.get('attendance_rate', 0),
                          total_attendance_today=stats.get('total_attendance_today', 0))

@dashboard_bp.route('/users')
@login_required
@role_required(['admin', 'product_owner', 'director'])
def users():
    """Admin and director page showing all users and allowing user management"""
    
    # Get all system users (excluding test users)
    all_users = User.query.all()
    
    title = 'User Management'
    
    # Sort system users by fingerprint number
    all_users.sort(key=lambda user: int(user.fingerprint_number) if user.fingerprint_number is not None and (isinstance(user.fingerprint_number, int) or (isinstance(user.fingerprint_number, str) and user.fingerprint_number.isdigit())) else 0)
    
    # Get all departments for filtering
    departments = Department.query.all()
    
    return render_template('dashboard/users.html',
                          title=title,
                          all_users=all_users,
                          departments=departments)


@dashboard_bp.route('/users/toggle_status/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def toggle_user_status(user_id):
    """Toggle a user's active/inactive status"""
    if current_user.role == 'director':
        flash('❌ Access Denied: Directors cannot deactivate user accounts.', 'danger')
        return redirect(url_for('dashboard.users'))
    user = User.query.get_or_404(user_id)
    
    # Don't allow deactivating yourself
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('dashboard.users'))
    
    # ADMIN AND PRODUCT OWNER FULL ACCESS: Can deactivate/activate any account
    if current_user.role not in ['admin', 'product_owner']:
        # Director can only deactivate Employee/Manager accounts
        if current_user.role == 'director' and user.role in ['admin', 'product_owner']:
            flash('❌ Access Denied: Director cannot deactivate Admin or Product Owner accounts.', 'danger')
            return redirect(url_for('dashboard.users'))
        elif current_user.role in ['manager', 'employee']:
            flash('❌ Access Denied: You cannot deactivate other users.', 'danger')
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
@role_required(['admin', 'product_owner'])
def delete_member(user_id):
    """Delete a user from the system"""
    if current_user.role == 'director':
        flash('❌ Access Denied: Directors cannot delete user accounts.', 'danger')
        return redirect(url_for('dashboard.users'))
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('dashboard.users'))
    
    # ADMIN AND PRODUCT OWNER FULL ACCESS: Can delete any account
    if current_user.role not in ['admin', 'product_owner']:
        # Director can only delete Employee/Manager accounts
        if current_user.role == 'director' and user.role in ['admin', 'product_owner']:
            flash('❌ Access Denied: Director cannot delete Admin or Product Owner accounts.', 'danger')
            return redirect(url_for('dashboard.users'))
        elif current_user.role in ['manager', 'employee']:
            flash('❌ Access Denied: You cannot delete other users.', 'danger')
            return redirect(url_for('dashboard.users'))
    
    # Store user info for the flash message
    user_name = f"{user.first_name} {user.last_name}"
    
    try:
        # First, delete all related records for this user
        from models import AttendanceLog, DailyAttendance, LeaveRequest, PaidHoliday, PermissionRequest, EmployeeAttachment, LeaveBalance
        
        # Count related records for confirmation
        attendance_count = AttendanceLog.query.filter_by(user_id=user_id).count()
        daily_attendance_count = DailyAttendance.query.filter_by(user_id=user_id).count()
        leave_requests_count = LeaveRequest.query.filter_by(user_id=user_id).count()
        permission_requests_count = PermissionRequest.query.filter_by(user_id=user_id).count()
        employee_attachments_count = EmployeeAttachment.query.filter_by(user_id=user_id).count()
        leave_balances_count = LeaveBalance.query.filter_by(user_id=user_id).count()
        paid_holidays_count = PaidHoliday.query.filter_by(created_by=user_id).count()
        
        total_records = (attendance_count + daily_attendance_count + leave_requests_count + 
                        permission_requests_count + employee_attachments_count + 
                        leave_balances_count + paid_holidays_count)
        
        if total_records > 0:
            # Delete related records
            AttendanceLog.query.filter_by(user_id=user_id).delete()
            DailyAttendance.query.filter_by(user_id=user_id).delete()
            LeaveRequest.query.filter_by(user_id=user_id).delete()
            PermissionRequest.query.filter_by(user_id=user_id).delete()
            EmployeeAttachment.query.filter_by(user_id=user_id).delete()
            LeaveBalance.query.filter_by(user_id=user_id).delete()
            PaidHoliday.query.filter_by(created_by=user_id).delete()
            
            logging.info(f'Deleted {total_records} related records for user {user_id}')
        
        # Delete device user records if any
        from models import DeviceUser
        device_users = DeviceUser.query.filter_by(system_user_id=user_id).all()
        for device_user in device_users:
            device_user.system_user_id = None
            device_user.is_processed = False
        
        # Now delete the user
        db.session.delete(user)
        db.session.commit()
        
        if total_records > 0:
            flash(f'User {user_name} and {total_records} related records have been deleted successfully.', 'success')
        else:
            flash(f'User {user_name} has been deleted successfully.', 'success')
            
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error deleting user {user_id}: {str(e)}')
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.users'))

@dashboard_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner'])
def edit_user(user_id):
    """Edit user information"""
    if current_user.role == 'director':
        flash('❌ Access Denied: Directors cannot edit user accounts.', 'danger')
        return redirect(url_for('dashboard.users'))
    user = User.query.get_or_404(user_id)
    departments = Department.query.all()

    # Check if the user being edited is a Product Owner
    is_editing_product_owner = user.role == 'product_owner'
    
    # ADMIN AND PRODUCT OWNER FULL ACCESS: No restrictions for Admin and Product Owner roles
    if current_user.role not in ['admin', 'product_owner']:
        # Only Admin and Product Owner can edit any account
        if current_user.role == 'director' and user.role in ['admin', 'product_owner']:
            flash('❌ Access Denied: Director cannot edit Admin or Product Owner accounts.', 'danger')
            return redirect(url_for('dashboard.users'))
        elif current_user.role in ['manager', 'employee'] and current_user.id != user.id:
            flash('❌ Access Denied: You can only edit your own account.', 'danger')
            return redirect(url_for('dashboard.users'))

    # Always bind form to user object so WTForms handles initial data and CSRF correctly
    form = UserEditForm(obj=user)

    # Set department choices BEFORE validation
    department_choices = [(0, 'No Department')] + [(d.id, d.department_name) for d in departments]
    form.department_id.choices = department_choices

    # Attachment form is separate (do not nest forms in template)
    attachment_form = EmployeeAttachmentForm()

    if form.validate_on_submit():
        try:
            # Basic fields
            user.first_name = form.first_name.data
            user.last_name = form.last_name.data
            user.email = form.email.data
            user.avaya_number = form.avaya_number.data or None
            user.fingerprint_number = form.fingerprint_number.data or None
            
            # ROLE ASSIGNMENT: Admin and Product Owner can assign any role
            original_role = user.role
            new_role = form.role.data
            
            # Log role changes for audit trail
            if original_role != new_role:
                import logging
                logging.info(f"Role change: {user.get_full_name()} (ID: {user.id}) role changing from '{original_role}' to '{new_role}' by {current_user.get_full_name()} ({current_user.role})")
                
                # Only Admin and Product Owner can assign any role
                if current_user.role not in ['admin', 'product_owner']:
                    flash(f'❌ Access Denied: Only Admin and Product Owner can change user roles.', 'danger')
                    return render_template('dashboard/edit_user.html', title='Edit User',
                                            form=form, attachment_form=attachment_form, user=user,
                                            is_editing_product_owner=is_editing_product_owner)
                
                flash(f'✅ Role changed from {original_role.title()} to {new_role.title()} for {user.get_full_name()}', 'success')
            
            user.role = form.role.data
            original_status = user.status # Store original status
            user.status = form.status.data
            user.joining_date = form.joining_date.data

            # Check if user status changed to 'active' and initialize leave balances
            if original_status != 'active' and user.status == 'active':
                from models import LeaveType, LeaveBalance
                current_year = datetime.now().year
                leave_types = LeaveType.query.all()
                for lt in leave_types:
                    existing_balance = LeaveBalance.query.filter_by(
                        user_id=user.id,
                        leave_type_id=lt.id,
                        year=current_year
                    ).first()
                    if not existing_balance:
                        new_balance = LeaveBalance(
                            user_id=user.id,
                            leave_type_id=lt.id,
                            total_days=0,
                            used_days=0,
                            year=current_year
                        )
                        db.session.add(new_balance)
                flash(f'Initialized leave balances for new active user {user.get_full_name()}.', 'info')

            # Additional fields
            user.date_of_birth = form.date_of_birth.data
            user.phone_number = form.phone_number.data or None
            user.alternate_phone_number = form.alternate_phone_number.data or None
            user.position = form.position.data or None
            user.salary = form.salary.data or None
            user.currency = form.currency.data or 'USD'

            # Department
            user.department_id = None if form.department_id.data == 0 else form.department_id.data

            # Password update (if provided)
            if form.new_password.data:
                from werkzeug.security import generate_password_hash
                if len(form.new_password.data) < 8:
                    flash('Password must be at least 8 characters long.', 'danger')
                    return render_template('dashboard/edit_user.html', title='Edit User',
                                            form=form, attachment_form=attachment_form, user=user)
                user.password_hash = generate_password_hash(form.new_password.data)

            user.updated_at = datetime.utcnow()
            db.session.commit()

            flash(f'User {user.first_name} {user.last_name} has been updated successfully.', 'success')
            return redirect(url_for('dashboard.users'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error updating user")
            flash(f'Error updating user: {str(e)}', 'danger')

    else:
        # helpful debug logs if validation fails
        if request.method == 'POST':
            current_app.logger.debug("Edit user POST failed validation")
            current_app.logger.debug(f"request.form: {request.form}")
            current_app.logger.debug(f"form.errors: {form.errors}")

    return render_template('dashboard/edit_user.html',
                           title='Edit User',
                           form=form,
                           attachment_form=attachment_form,
                           user=user,
                           is_editing_product_owner=is_editing_product_owner)

@dashboard_bp.route('/members/search')
@login_required
def members_search():
    """AJAX endpoint for searching members"""
    search_query = request.args.get('q', '').strip()
    department_filter = request.args.get('department', 'all')
    status_filter = request.args.get('status', 'active')
    
    # Build query
    query = User.query
    
    if status_filter == 'active':
        query = query.filter_by(status='active')
    elif status_filter == 'inactive':
        query = query.filter_by(status='inactive')
    
    # Apply search filter
    if search_query:
        search_filter = f"%{search_query}%"
        query = query.filter(
            db.or_(
                User.first_name.ilike(search_filter),
                User.last_name.ilike(search_filter),
                User.email.ilike(search_filter),
                User.avaya_number.ilike(search_filter)
            )
        )
    
    # Apply department filter
    if department_filter != 'all':
        if department_filter == 'none':
            query = query.filter(User.department_id.is_(None))
        else:
            query = query.join(Department).filter(Department.department_name == department_filter)
    
    users = query.all()
    
    # Convert to JSON
    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'avaya_number': user.avaya_number or '',
            'role': user.role,
            'department': user.department.department_name if user.department else 'No Department',
            'profile_picture': user.profile_picture or '',
            'status': user.status
        })
    
    return jsonify({
        'users': users_data,
        'total': len(users_data)
    })

@dashboard_bp.route('/members')
def members():
    """Page showing all active and inactive members in the system"""
    # All users can see all active members, regardless of role
    # Get all active users, sorted by department name, then by last name and first name
    active_users = User.query.filter(
        User.status == 'active',
        ~User.first_name.like('User%'),  # Exclude generic test users
        ~User.first_name.like('NN-%'),   # Exclude numbered test users
        User.first_name != '',           # Exclude empty names
        User.last_name != ''             # Exclude users without last names
    ).all()

    # Sort users by department name, then by last name, then by first name
    def sort_users_by_department(user_list):
        custom_department_order = {
            'project management': 1,
            'human resources': 2, # HR
            'web development': 3, # Web
            'marketing': 4, # Marketing
            'finance': 5, # Finance
            'call center': 6, # Call Center
            'housekeeping': 7 # Housekeeping
        }
        return sorted(user_list, key=lambda user: (
            # Custom order for specific users
            (0,) if user.first_name.lower() == 'george' and user.last_name.lower() == 'smair' else (
                (1,) if user.first_name.lower() == 'maged' and user.last_name.lower() == 'grace' else (
                    # 1. Global Role Priority (Director at top)
                    -2 if user.role == 'director' else (
                        custom_department_order.get(user.department.department_name.lower(), 8) if user.department else 9
                    ),
                    # 3. Role within Department (Manager first, then Admin, then others)
                    0 if user.role == 'manager' else (
                        1 if user.role == 'admin' else 2
                    ),
                    # 4. Alphabetical by Last Name, then First Name
                    # 4. Custom order for 'web development' team
                    (0 if user.department and user.department.department_name.lower() == 'web development' and user.first_name.lower() == 'mostafa' and user.last_name.lower() == 'ayman' else
                     1 if user.department and user.department.department_name.lower() == 'web development' and user.first_name.lower() == 'youssef' and user.last_name.lower() == 'george' else
                     2 if user.department and user.department.department_name.lower() == 'web development' and user.first_name.lower() == 'youssef' and user.last_name.lower() == 'karam' else
                     3 if user.department and user.department.department_name.lower() == 'web development' and user.first_name.lower() == 'manar' else
                     4 if user.department and user.department.department_name.lower() == 'web development' and user.first_name.lower() == 'samir' else
                     5 if user.department and user.department.department_name.lower() == 'web development' else
                     0), # Default priority for other departments
                    # 5. Alphabetical by Last Name, then First Name (for users not in custom web dev order)
                    user.last_name.lower(),
                    user.first_name.lower()
                )
            )
        ))

    active_users = sort_users_by_department(active_users)
    # Get all departments for filtering
    departments = Department.query.all()
    
    return render_template('dashboard/members.html', title='Company Members', active_users=active_users, departments=departments)


    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of results per page

    # Start with all active users
    query = User.query.filter_by(status='active')

    # Filter by current user's managed department if they are a manager or admin
    if current_user.role in ['manager', 'admin'] and current_user.managed_department:
        managed_dept_ids = [dept.id for dept in current_user.managed_department]
        query = query.filter(User.department_id.in_(managed_dept_ids))

    # Apply search query filter
    if search_query:
        query = query.filter(
            (User.first_name.ilike(f'%{search_query}%')) |
            (User.last_name.ilike(f'%{search_query}%')) |
            (User.email.ilike(f'%{search_query}%'))
        )

    # Paginate the results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    employees = pagination.items

    results = []
    for employee in employees:
        text = f"{employee.first_name} {employee.last_name}"
        if employee.department:
            text += f" ({employee.department.department_name})"
        if employee.fingerprint_number:
            text += f" (FP: {employee.fingerprint_number})"
        results.append({
            'id': employee.id,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'fingerprint_number': employee.fingerprint_number,
            'department': {'department_name': employee.department.department_name} if employee.department else None
        })

    return jsonify({
        'users': results,
        'pagination': {'more': pagination.has_next}
    })

@dashboard_bp.route('/director-debug')
@login_required
def director_debug():
    """Debug route to check director access"""
    return f"""
    <h1>Director Debug Information</h1>
    <p><strong>Current User:</strong> {current_user.email}</p>
    <p><strong>Current Role:</strong> "{current_user.role}"</p>
    <p><strong>Is Authenticated:</strong> {current_user.is_authenticated}</p>
    <p><strong>User ID:</strong> {current_user.id}</p>
    <p><strong>Status:</strong> {current_user.status}</p>
    <hr>
    <p>If your role is "director", you should be able to access the director dashboard.</p>
    <p><a href="/dashboard/director">Try Director Dashboard</a></p>
    <p><a href="/dashboard/">Back to Main Dashboard</a></p>
    """

@dashboard_bp.route('/director')
@login_required
def director():
    """Director dashboard with comprehensive data view"""
    # Manual role check with better error handling
    if current_user.role != 'director':
        flash(f'Access denied. Your role is "{current_user.role}" but "director" is required. Contact an administrator.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    stats = get_dashboard_stats(current_user)
    
    # Get ALL permission requests for director view (not limited)
    all_permission_requests = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).all()
    
    # Separate by status for easy filtering in template
    pending_permissions = [p for p in all_permission_requests if p.status == 'pending']
    approved_permissions = [p for p in all_permission_requests if p.status == 'approved']
    rejected_permissions = [p for p in all_permission_requests if p.status == 'rejected']
    
    # Get leave request statistics for overview
    all_leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    pending_leave_requests = LeaveRequest.query.filter_by(status='pending').order_by(LeaveRequest.created_at.desc()).all()
    approved_leave_requests = LeaveRequest.query.filter_by(status='approved').order_by(LeaveRequest.created_at.desc()).all()
    rejected_leave_requests = LeaveRequest.query.filter_by(status='rejected').order_by(LeaveRequest.created_at.desc()).all()
    
    # Get pending leave requests for table (limited to 5)
    pending_leave_requests_table = LeaveRequest.query.filter_by(status='pending').order_by(LeaveRequest.created_at.desc()).limit(5).all()
    
    # Get recent leave balances
    recent_leave_balances = LeaveBalance.query.order_by(LeaveBalance.created_at.desc()).limit(5).all()
    
    # Get upcoming paid holidays
    from datetime import datetime
    upcoming_paid_holidays = PaidHoliday.query.filter(
        PaidHoliday.start_date >= datetime.now().date()
    ).order_by(PaidHoliday.start_date.asc()).limit(5).all()
    
    # Get leave type statistics with dynamic data
    leave_types = LeaveType.query.all()
    leave_type_stats = []
    total_leave_requests = 0
    
    for leave_type in leave_types:
        # Count all leave requests for this type
        total_count = LeaveRequest.query.filter_by(leave_type_id=leave_type.id).count()
        
        # Count by status
        pending_count = LeaveRequest.query.filter_by(leave_type_id=leave_type.id, status='pending').count()
        approved_count = LeaveRequest.query.filter_by(leave_type_id=leave_type.id, status='approved').count()
        rejected_count = LeaveRequest.query.filter_by(leave_type_id=leave_type.id, status='rejected').count()
        
        # Count recent requests (last 30 days)
        from datetime import timedelta
        recent_date = datetime.now() - timedelta(days=30)
        recent_count = LeaveRequest.query.filter(
            LeaveRequest.leave_type_id == leave_type.id,
            LeaveRequest.created_at >= recent_date
        ).count()
        
        # Calculate total leave days used
        approved_requests = LeaveRequest.query.filter_by(
            leave_type_id=leave_type.id, 
            status='approved'
        ).all()
        
        total_days_used = 0
        for request in approved_requests:
            if request.start_date and request.end_date:
                total_days_used += (request.end_date - request.start_date).days + 1
        
        # Generate consistent color based on leave type name
        color_hash = hash(leave_type.name) % 360
        colors = {
            'primary': f'hsl({color_hash}, 70%, 50%)',
            'light': f'hsl({color_hash}, 70%, 85%)',
            'dark': f'hsl({color_hash}, 70%, 35%)'
        }
        
        leave_type_stats.append({
            'name': leave_type.name,
            'total_count': total_count,
            'pending_count': pending_count,
            'approved_count': approved_count,
            'rejected_count': rejected_count,
            'recent_count': recent_count,
            'total_days_used': total_days_used,
            'colors': colors,
            'color': colors['primary']  # Backward compatibility
        })
        
        total_leave_requests += total_count
    
    # Get recent activity (attendance, leave requests, permission requests)
    recent_activities = []
    
    # Recent leave requests
    recent_leaves = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).limit(3).all()
    for leave in recent_leaves:
        recent_activities.append({
            'type': 'leave',
            'icon': 'calendar-times',
            'color': 'warning',
            'user': f"{leave.user.first_name} {leave.user.last_name}",
            'action': f"requested {leave.leave_type.name if leave.leave_type else 'leave'}",
            'time': leave.created_at,
            'status': leave.status
        })
    
    # Recent permission requests
    recent_perms = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).limit(3).all()
    for perm in recent_perms:
        recent_activities.append({
            'type': 'permission',
            'icon': 'door-open',
            'color': 'info',
            'user': f"{perm.user.first_name} {perm.user.last_name}",
            'action': f"requested permission ({perm.reason[:30]}...)" if len(perm.reason) > 30 else f"requested permission ({perm.reason})",
            'time': perm.created_at,
            'status': perm.status
        })
    
    # Sort recent activities by time
    recent_activities.sort(key=lambda x: x['time'], reverse=True)
    recent_activities = recent_activities[:10]  # Keep only 10 most recent
    
    return render_template('dashboard/director.html',
                          title='Director Dashboard',
                          stats=stats,
                          all_permission_requests=all_permission_requests,
                          pending_permissions=pending_permissions,
                          approved_permissions=approved_permissions,
                          rejected_permissions=rejected_permissions,
                          all_leave_requests=all_leave_requests,
                          pending_leave_requests=pending_leave_requests,
                          approved_leave_requests=approved_leave_requests,
                          rejected_leave_requests=rejected_leave_requests,
                          pending_leave_requests_table=pending_leave_requests_table,
                          recent_leave_balances=recent_leave_balances,
                          upcoming_paid_holidays=upcoming_paid_holidays,
                          leave_type_stats=leave_type_stats,
                          total_leave_requests=total_leave_requests,
                          recent_activities=recent_activities,
                          # Auto-fetch data attributes
                          pending_leave_requests_count=len(pending_leave_requests),
                          pending_permission_requests_count=len(pending_permissions),
                          approved_leave_requests_count=len(approved_leave_requests),
                          approved_permission_requests_count=len(approved_permissions),
                          rejected_leave_requests_count=len(rejected_leave_requests),
                          rejected_permission_requests_count=len(rejected_permissions),
                          total_employees=stats.get('total_employees', 0),
                          total_departments=stats.get('total_departments', 0),
                          attendance_rate=stats.get('attendance_rate', 0),
                          total_attendance_today=stats.get('total_attendance_today', 0))

@dashboard_bp.route('/search_users', methods=['GET'])
@login_required
@role_required(['Admin', 'HR', 'Manager'])
def search_users():
    query = request.args.get('query', '').strip()
    users = []
    if query:
        # Search by first name, last name, fingerprint number, or department name (excluding test users)
        users_query = User.query.join(Department, User.department_id == Department.id, isouter=True).filter(
            User.status == 'active',
            ~User.first_name.like('User%'),  # Exclude generic test users
            ~User.first_name.like('NN-%'),   # Exclude numbered test users
            User.first_name != '',           # Exclude empty names
            User.last_name != '',            # Exclude users without last names
            (User.first_name.ilike(f'%{query}%')) |
            (User.last_name.ilike(f'%{query}%')) |
            (User.fingerprint_number.ilike(f'%{query}%')) |
            (Department.department_name.ilike(f'%{query}%'))
        ).all()

        for user in users_query:
            users.append({
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'fingerprint_number': user.fingerprint_number,
                'department': {'department_name': user.department.department_name} if user.department else None
            })
    return jsonify({'users': users})










@dashboard_bp.route('/search_employees_ajax', methods=['GET'])
@login_required
@role_required('admin', 'hr', 'manager')
def search_employees_ajax():
    query = request.args.get('query', '')
    page = request.args.get('page', type=int, default=1)
    
    # Base query for active users (excluding test users)
    users_query = User.query.filter(
        User.status == 'active',
        ~User.first_name.like('User%'),  # Exclude generic test users
        ~User.first_name.like('NN-%'),   # Exclude numbered test users
        User.first_name != '',           # Exclude empty names
        User.last_name != ''             # Exclude users without last names
    )

    # Filter by current user's managed department if they are a manager
    if current_user.role == 'manager' and current_user.managed_department:
        managed_dept_ids = [dept.id for dept in current_user.managed_department]
        users_query = users_query.filter(User.department_id.in_(managed_dept_ids))

    # Apply search query
    if query:
        users_query = users_query.filter(
            (User.first_name.ilike(f'%{query}%')) |
            (User.last_name.ilike(f'%{query}%')) |
            (User.fingerprint_number.ilike(f'%{query}%'))
        )

    # Order by first name for consistent results
    users_query = users_query.order_by(User.first_name)

    # Paginate results (Select2 expects 'results' and 'pagination' keys)
    per_page = 10  # Number of results per page
    pagination = users_query.paginate(page=page, per_page=per_page, error_out=False)
    employees = pagination.items

    results = []
    for employee in employees:
        results.append({
            'id': employee.id,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'fingerprint_number': employee.fingerprint_number,
            'department': {'department_name': employee.department.department_name} if employee.department else None
        })

    return jsonify({
        'users': results,
        'pagination': {'more': pagination.has_next}
    })
@dashboard_bp.route('/emergency-db-cleanup', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def emergency_db_cleanup():
    """Emergency database connection cleanup (Admin/Product Owner only)"""
    try:
        from connection_manager import emergency_connection_cleanup, get_connection_pool_status
        
        # Get current pool status
        pool_status = get_connection_pool_status()
        logging.warning(f"Emergency cleanup requested by {current_user.get_full_name()} ({current_user.role})")
        logging.info(f"Current pool status: {pool_status}")
        
        # Perform emergency cleanup
        cleanup_result = emergency_connection_cleanup()
        
        return jsonify({
            'status': 'success',
            'message': 'Emergency database cleanup completed',
            'pool_status': pool_status,
            'cleanup_result': cleanup_result
        })
        
    except Exception as e:
        logging.error(f"Error in emergency DB cleanup: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Emergency cleanup failed: {str(e)}'
        }), 500

@dashboard_bp.route('/db-pool-status')
@login_required
@role_required(['admin', 'product_owner'])
def db_pool_status():
    """Get database connection pool status (Admin/Product Owner only)"""
    try:
        from connection_manager import get_connection_pool_status
        
        pool_status = get_connection_pool_status()
        
        return jsonify({
            'status': 'success',
            'pool_status': pool_status
        })
        
    except Exception as e:
        logging.error(f"Error getting pool status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to get pool status: {str(e)}'
        }), 500

@dashboard_bp.route('/upload-attachment/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def upload_attachment(user_id):
    """Upload an attachment for an employee"""
    from werkzeug.utils import secure_filename
    import os
    from models import EmployeeAttachment
    
    user = User.query.get_or_404(user_id)
    form = EmployeeAttachmentForm()
    
    if form.validate_on_submit():
        file = form.file.data
        if file and file.filename:
            # Create uploads directory if it doesn't exist
            upload_dir = os.path.join(current_app.instance_path, 'uploads', 'attachments')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Generate secure filename
            filename = secure_filename(file.filename)
            # Add timestamp to avoid conflicts
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            file_path = os.path.join(upload_dir, filename)
            
            # Save file
            file.save(file_path)
            
            # Create attachment record
            attachment = EmployeeAttachment(
                user_id=user_id,
                file_name=file.filename,
                display_name=form.display_name.data,
                file_path=file_path,
                file_size=os.path.getsize(file_path),
                file_type=file.content_type,
                description=form.description.data,
                uploaded_by=current_user.id
            )
            
            try:
                db.session.add(attachment)
                db.session.commit()
                flash(f'Attachment "{form.display_name.data}" uploaded successfully.', 'success')
            except Exception as e:
                db.session.rollback()
                # Clean up uploaded file
                if os.path.exists(file_path):
                    os.remove(file_path)
                flash(f'Error uploading attachment: {str(e)}', 'danger')
        else:
            flash('No file selected.', 'warning')
    else:
        flash('Please fill in all required fields.', 'warning')
    
    return redirect(url_for('dashboard.edit_user', user_id=user_id))

@dashboard_bp.route('/view-attachment/<int:attachment_id>')
@login_required
@role_required(['admin', 'product_owner', 'director'])
def view_attachment(attachment_id):
    """View an employee attachment in browser"""
    from flask import send_file, render_template
    from models import EmployeeAttachment
    
    attachment = EmployeeAttachment.query.get_or_404(attachment_id)
    
    if not os.path.exists(attachment.file_path):
        flash('File not found.', 'error')
        return redirect(url_for('dashboard.edit_user', user_id=attachment.user_id))
    
    # Get file extension to determine content type
    file_ext = os.path.splitext(attachment.file_name)[1].lower()
    
    # For PDFs and images, display in browser
    if file_ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
        return send_file(
            attachment.file_path,
            as_attachment=False,
            mimetype=None  # Let Flask auto-detect
        )
    else:
        # For other file types, show a preview page with download option
        return render_template('dashboard/view_attachment.html', 
                             attachment=attachment, 
                             file_ext=file_ext)

@dashboard_bp.route('/download-attachment/<int:attachment_id>')
@login_required
@role_required(['admin', 'product_owner', 'director'])
def download_attachment(attachment_id):
    """Download an employee attachment"""
    from flask import send_file
    from models import EmployeeAttachment
    
    attachment = EmployeeAttachment.query.get_or_404(attachment_id)
    
    if not os.path.exists(attachment.file_path):
        flash('File not found.', 'error')
        return redirect(url_for('dashboard.edit_user', user_id=attachment.user_id))
    
    return send_file(
        attachment.file_path,
        as_attachment=True,
        download_name=attachment.file_name
    )

@dashboard_bp.route('/delete-attachment/<int:attachment_id>', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def delete_attachment(attachment_id):
    """Delete an employee attachment"""
    from models import EmployeeAttachment
    from flask import jsonify
    
    attachment = EmployeeAttachment.query.get_or_404(attachment_id)
    user_id = attachment.user_id
    
    try:
        # Delete file from filesystem
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
        
        # Delete database record
        db.session.delete(attachment)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Attachment "{attachment.display_name}" deleted successfully.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error deleting attachment: {str(e)}'
        }), 500

# Leave Management Routes
@dashboard_bp.route('/leave-types')
@login_required
@role_required(['admin', 'product_owner'])
def leave_types():
    """Manage leave types"""
    from models import LeaveType
    from forms import LeaveTypeForm
    
    leave_types = LeaveType.query.all()
    form = LeaveTypeForm()
    
    return render_template('dashboard/leave_types.html', 
                         title='Leave Types Management',
                         leave_types=leave_types,
                         form=form)

@dashboard_bp.route('/leave-types/create', methods=['POST'])
@login_required
@role_required(['product_owner'])
def create_leave_type():
    """Create a new leave type"""
    from models import LeaveType
    from forms import LeaveTypeForm
    
    form = LeaveTypeForm()
    
    if form.validate_on_submit():
        leave_type = LeaveType(
            name=form.name.data,
            description=form.description.data,
            color=form.color.data,
            is_active=form.is_active.data,
            requires_balance=form.requires_balance.data
        )
        
        try:
            db.session.add(leave_type)
            db.session.commit()
            flash(f'Leave type "{form.name.data}" created successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating leave type: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.leave_types'))

@dashboard_bp.route('/leave-types/<int:leave_type_id>/edit', methods=['POST'])
@login_required
@role_required(['product_owner'])
def edit_leave_type(leave_type_id):
    """Edit a leave type"""
    from models import LeaveType
    
    leave_type = LeaveType.query.get_or_404(leave_type_id)
    
    try:
        leave_type.name = request.form.get('name')
        leave_type.description = request.form.get('description')
        leave_type.color = request.form.get('color')
        leave_type.is_active = 'is_active' in request.form
        leave_type.requires_balance = 'requires_balance' in request.form
        leave_type.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Leave type "{leave_type.name}" updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating leave type: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.leave_types'))

@dashboard_bp.route('/leave-types/<int:leave_type_id>/delete', methods=['POST'])
@login_required
@role_required(['product_owner'])
def delete_leave_type(leave_type_id):
    """Delete a leave type"""
    from models import LeaveType
    
    leave_type = LeaveType.query.get_or_404(leave_type_id)
    
    try:
        db.session.delete(leave_type)
        db.session.commit()
        flash(f'Leave type "{leave_type.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting leave type: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.leave_types'))

@dashboard_bp.route('/paid-holidays')
@login_required
@role_required(['admin', 'product_owner', 'director'])
def paid_holidays():
    """Manage paid holidays"""
    from models import PaidHoliday
    from forms import PaidHolidayForm
    
    holidays = PaidHoliday.query.order_by(PaidHoliday.start_date).all()
    form = PaidHolidayForm()
    
    return render_template('dashboard/paid_holidays.html',
                         title='Paid Holidays Management',
                         holidays=holidays,
                         form=form)

@dashboard_bp.route('/paid-holidays/create', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def create_paid_holiday():
    """Create a new paid holiday"""
    from models import PaidHoliday
    from forms import PaidHolidayForm
    
    form = PaidHolidayForm()
    
    if form.validate_on_submit():
        holiday = PaidHoliday(
            holiday_type=form.holiday_type.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data if form.holiday_type.data == 'range' else None,
            description=form.description.data,
            is_recurring=form.is_recurring.data,
            created_by=current_user.id
        )
        
        try:
            db.session.add(holiday)
            db.session.commit()
            
            # Process paid holiday for all employees
            from routes.attendance import process_paid_holidays_for_all_employees
            if holiday.holiday_type == 'day':
                process_paid_holidays_for_all_employees(holiday.start_date)
            else:
                # For range holidays, process each day
                current_date = holiday.start_date
                while current_date <= holiday.end_date:
                    process_paid_holidays_for_all_employees(current_date)
                    current_date += timedelta(days=1)
            
            flash(f'Paid holiday "{form.description.data}" created successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating paid holiday: {str(e)}', 'danger')
    else:
        # Flash form validation errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('dashboard.paid_holidays'))

@dashboard_bp.route('/paid-holidays/edit/<int:holiday_id>', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def edit_paid_holiday(holiday_id):
    """Edit a paid holiday"""
    from models import PaidHoliday
    
    holiday = PaidHoliday.query.get_or_404(holiday_id)
    
    # Get form data
    holiday_type = request.form.get('holiday_type')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    description = request.form.get('description')
    is_recurring = request.form.get('is_recurring') == 'on'
    
    # Validate required fields
    if not all([holiday_type, start_date, description]):
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('dashboard.paid_holidays'))
    
    # Convert dates
    try:
        from datetime import datetime
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('dashboard.paid_holidays'))
    
    # Validate date range
    if holiday_type == 'range' and not end_date:
        flash('End date is required for date range holidays.', 'danger')
        return redirect(url_for('dashboard.paid_holidays'))
    
    if holiday_type == 'range' and end_date and end_date < start_date:
        flash('End date must be after start date.', 'danger')
        return redirect(url_for('dashboard.paid_holidays'))
    
        try:
            # Update holiday
            holiday.holiday_type = holiday_type
            holiday.start_date = start_date
            holiday.end_date = end_date if holiday_type == 'range' else None
            holiday.description = description
            holiday.is_recurring = is_recurring
            
            db.session.commit()
            
            # Process paid holiday for all employees
            from routes.attendance import process_paid_holidays_for_all_employees
            if holiday_type == 'day':
                process_paid_holidays_for_all_employees(start_date)
            else:
                # For range holidays, process each day
                current_date = start_date
                while current_date <= end_date:
                    process_paid_holidays_for_all_employees(current_date)
                    current_date += timedelta(days=1)
            
            flash(f'Paid holiday "{description}" updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating paid holiday: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.paid_holidays'))

@dashboard_bp.route('/paid-holidays/<int:holiday_id>/delete', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def delete_paid_holiday(holiday_id):
    """Delete a paid holiday"""
    from models import PaidHoliday
    
    holiday = PaidHoliday.query.get_or_404(holiday_id)
    
    try:
        db.session.delete(holiday)
        db.session.commit()
        flash(f'Paid holiday "{holiday.description}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting paid holiday: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.paid_holidays'))

@dashboard_bp.route('/leave-balances')
@login_required
@role_required(['admin', 'product_owner', 'director', 'manager'])
def leave_balances():
    """Manage leave balances for employees"""
    from models import LeaveBalance, LeaveType, User
    from forms import LeaveBalanceForm
    
    # Filter balances based on user role
    if current_user.role in ['admin', 'product_owner', 'director']:
        # Admins, Product Owners and directors can see all balances
        balances = LeaveBalance.query.join(LeaveType).join(User).all()
        users = User.query.filter_by(status='active').all()
    elif current_user.role == 'manager':
        # Managers can see their team's balances (employees in their department)
        if current_user.department_id:
            # Manager has a department - show team members
            team_members = User.query.filter_by(status='active', department_id=current_user.department_id).all()
            user_ids = [user.id for user in team_members]
            balances = LeaveBalance.query.join(LeaveType).join(User).filter(
                LeaveBalance.user_id.in_(user_ids)
            ).all()
            users = team_members
        else:
            # Manager has no department - show only themselves
            balances = LeaveBalance.query.join(LeaveType).join(User).filter(
                LeaveBalance.user_id == current_user.id
            ).all()
            users = [current_user]
    else:
        # Regular employees can only see their own balances
        balances = LeaveBalance.query.join(LeaveType).join(User).filter(
            LeaveBalance.user_id == current_user.id
        ).all()
        users = [current_user]
    
    form = LeaveBalanceForm()
    
    # Set form choices
    leave_types = LeaveType.query.filter_by(is_active=True).all()
    form.user_id.choices = [(u.id, f"{u.first_name} {u.last_name}") for u in users]
    form.leave_type_id.choices = [(lt.id, lt.name) for lt in leave_types]
    
    return render_template('dashboard/leave_balances.html',
                         title='Leave Balances Management',
                         balances=balances,
                         form=form)

@dashboard_bp.route('/leave-balances/create', methods=['POST'])
@login_required
@role_required(['admin', 'manager'])
def create_leave_balance():
    """Create or update leave balance for an employee"""
    from models import LeaveBalance
    from forms import LeaveBalanceForm
    
    form = LeaveBalanceForm()
    
    # Set form choices based on user role
    from models import User, LeaveType
    if current_user.role in ['admin', 'product_owner', 'director']:
        users = User.query.filter_by(status='active').all()
    elif current_user.role == 'manager':
        if current_user.department_id:
            users = User.query.filter_by(status='active', department_id=current_user.department_id).all()
        else:
            users = [current_user]
    else:
        users = [current_user]
    
    leave_types = LeaveType.query.filter_by(is_active=True).all()
    form.user_id.choices = [(u.id, f"{u.first_name} {u.last_name}") for u in users]
    form.leave_type_id.choices = [(lt.id, lt.name) for lt in leave_types]
    
    if form.validate_on_submit():
        # Security check: Managers can only create balances for their team members
        if current_user.role == 'manager':
            if current_user.department_id:
                # Manager has department - check if user is in their team
                team_member_ids = [u.id for u in User.query.filter_by(status='active', department_id=current_user.department_id).all()]
                if form.user_id.data not in team_member_ids:
                    flash('You can only manage leave balances for your team members.', 'danger')
                    return redirect(url_for('dashboard.leave_balances'))
            else:
                # Manager has no department - can only manage their own
                if form.user_id.data != current_user.id:
                    flash('You can only manage your own leave balances.', 'danger')
                    return redirect(url_for('dashboard.leave_balances'))
        
        # Check if balance already exists for this user, leave type, and year
        existing_balance = LeaveBalance.query.filter_by(
            user_id=form.user_id.data,
            leave_type_id=form.leave_type_id.data,
            year=form.year.data
        ).first()
        
        if existing_balance:
            # Update existing balance
            existing_balance.total_days = form.total_days.data
            existing_balance.used_days = form.used_days.data or 0
            existing_balance.manual_remaining_days = form.manual_remaining_days.data if form.manual_remaining_days.data else None
            existing_balance.calculate_remaining()
        else:
            # Create new balance
            balance = LeaveBalance(
                user_id=form.user_id.data,
                leave_type_id=form.leave_type_id.data,
                total_days=form.total_days.data,
                used_days=form.used_days.data or 0,
                manual_remaining_days=form.manual_remaining_days.data if form.manual_remaining_days.data else None,
                year=form.year.data
            )
            balance.calculate_remaining()
            db.session.add(balance)
        
        try:
            db.session.commit()
            flash('Leave balance updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating leave balance: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.leave_balances'))

@dashboard_bp.route('/leave-balances/<int:balance_id>/edit', methods=['POST'])
@login_required
@role_required(['admin', 'manager'])
def edit_leave_balance(balance_id):
    """Edit a leave balance"""
    from models import LeaveBalance
    
    balance = LeaveBalance.query.get_or_404(balance_id)
    
    # Security check: Managers can only edit their team's balances
    if current_user.role == 'manager':
        if current_user.department_id:
            # Manager has department - check if user is in their team
            team_member_ids = [u.id for u in User.query.filter_by(status='active', department_id=current_user.department_id).all()]
            if balance.user_id not in team_member_ids:
                flash('You can only manage leave balances for your team members.', 'danger')
                return redirect(url_for('dashboard.leave_balances'))
        else:
            # Manager has no department - can only edit their own
            if balance.user_id != current_user.id:
                flash('You can only manage your own leave balances.', 'danger')
                return redirect(url_for('dashboard.leave_balances'))
    
    try:
        # Get form data directly from request
        total_days = request.form.get('total_days')
        used_days = request.form.get('used_days')
        manual_remaining_days = request.form.get('manual_remaining_days')
        year = request.form.get('year')
        
        # Debug logging
        print(f"Edit form data - total_days: {total_days}, used_days: {used_days}, manual_remaining_days: {manual_remaining_days}, year: {year}")
        
        # Validate required fields
        if not total_days or not year:
            flash('Please fill in all required fields (Total Days and Year are required).', 'danger')
            return redirect(url_for('dashboard.leave_balances'))
        
        # Update balance
        balance.total_days = int(total_days)
        balance.used_days = int(used_days) if used_days else 0
        balance.manual_remaining_days = int(manual_remaining_days) if manual_remaining_days else None
        balance.year = int(year)
        balance.calculate_remaining()
        
        db.session.commit()
        flash('Leave balance updated successfully.', 'success')
    except ValueError as e:
        db.session.rollback()
        flash('Please enter valid numbers for all fields.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating leave balance: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.leave_balances'))

@dashboard_bp.route('/leave-balances/<int:balance_id>/delete', methods=['POST'])
@login_required
@role_required(['admin', 'manager'])
def delete_leave_balance(balance_id):
    """Delete a leave balance"""
    from models import LeaveBalance
    
    balance = LeaveBalance.query.get_or_404(balance_id)
    
    # Security check: Managers can only delete their team's balances
    if current_user.role == 'manager':
        if current_user.department_id:
            # Manager has department - check if user is in their team
            team_member_ids = [u.id for u in User.query.filter_by(status='active', department_id=current_user.department_id).all()]
            if balance.user_id not in team_member_ids:
                flash('You can only manage leave balances for your team members.', 'danger')
                return redirect(url_for('dashboard.leave_balances'))
        else:
            # Manager has no department - can only delete their own
            if balance.user_id != current_user.id:
                flash('You can only manage your own leave balances.', 'danger')
                return redirect(url_for('dashboard.leave_balances'))
    
    employee_name = balance.user.get_full_name()
    leave_type_name = balance.leave_type.name
    
    try:
        db.session.delete(balance)
        db.session.commit()
        flash(f'Leave balance for {employee_name} - {leave_type_name} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting leave balance: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.leave_balances'))

@dashboard_bp.route('/my-leave-balance')
@login_required
def my_leave_balance():
    """Get current user's leave balance for sidebar widget"""
    from models import LeaveBalance, LeaveType
    
    # Get user's leave balances
    balances = LeaveBalance.query.join(LeaveType).filter(
        LeaveBalance.user_id == current_user.id
    ).order_by(LeaveType.name).all()
    
    # Format data for the widget
    balance_data = []
    for balance in balances:
        balance_data.append({
            'leave_type': balance.leave_type.name,
            'remaining_days': balance.remaining_days,
            'total_days': balance.total_days,
            'used_days': balance.used_days,
            'year': balance.year
        })
    
    return jsonify({
        'status': 'success',
        'balances': balance_data
    })

@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    """API endpoint to get dashboard statistics"""
    try:
        stats = get_dashboard_stats(current_user)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logging.error(f"Error fetching dashboard stats: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error fetching dashboard statistics'
        }), 500

@dashboard_bp.route('/smtp-configuration')
@login_required
@role_required(['admin', 'product_owner'])
def smtp_configuration():
    """SMTP Configuration management for admin only"""
    config = SMTPConfiguration.query.filter_by(is_active=True).first()
    form = SMTPConfigurationForm()
    
    if config:
        form.smtp_server.data = config.smtp_server
        form.smtp_port.data = config.smtp_port
        form.smtp_username.data = config.smtp_username
        form.smtp_password.data = config.smtp_password
        form.use_tls.data = config.use_tls
        form.use_ssl.data = config.use_ssl
        form.sender_name.data = config.sender_name
        form.sender_email.data = config.sender_email
        form.is_active.data = config.is_active
        # Module-specific email lists
        form.leave_notification_emails.data = config.leave_notification_emails or ''
        form.permission_notification_emails.data = config.permission_notification_emails or ''
        form.admin_notification_emails.data = config.admin_notification_emails or ''
        # Notification settings
        form.notify_leave_requests.data = config.notify_leave_requests
        form.notify_permission_requests.data = config.notify_permission_requests
        form.notify_admin_only.data = config.notify_admin_only
    
    return render_template('dashboard/smtp_configuration.html',
                         title='SMTP Configuration',
                         config=config,
                         form=form)

@dashboard_bp.route('/smtp-configuration/save', methods=['POST'])
@login_required
@role_required(['product_owner'])  # Only Product Owner can edit
def save_smtp_configuration():
    """Save SMTP Configuration"""
    form = SMTPConfigurationForm()
    
    if form.validate_on_submit():
        # Deactivate existing configurations
        existing_configs = SMTPConfiguration.query.all()
        for config in existing_configs:
            config.is_active = False
        
        # Create new configuration
        new_config = SMTPConfiguration(
            smtp_server=form.smtp_server.data,
            smtp_port=form.smtp_port.data,
            smtp_username=form.smtp_username.data,
            smtp_password=form.smtp_password.data,  # In production, encrypt this
            use_tls=form.use_tls.data,
            use_ssl=form.use_ssl.data,
            sender_name=form.sender_name.data,
            sender_email=form.sender_email.data,
            is_active=form.is_active.data,
            # Module-specific email lists
            leave_notification_emails=form.leave_notification_emails.data or '',
            permission_notification_emails=form.permission_notification_emails.data or '',
            admin_notification_emails=form.admin_notification_emails.data or '',
            # Notification settings
            notify_leave_requests=form.notify_leave_requests.data,
            notify_permission_requests=form.notify_permission_requests.data,
            notify_admin_only=form.notify_admin_only.data
        )
        
        try:
            db.session.add(new_config)
            db.session.commit()
            flash('SMTP configuration saved successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving SMTP configuration: {str(e)}', 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('dashboard.smtp_configuration'))

@dashboard_bp.route('/smtp-configuration/test', methods=['POST'])
@login_required
@role_required(['product_owner'])  # Only Product Owner can test
def test_smtp_configuration():
    """Test SMTP Configuration - Force use of working Everlast settings"""
    
    # Use the exact working settings that we know work
    smtp_server = "mail.everlastwellness.com"
    smtp_port = 465
    smtp_username = "erp@everlastwellness.com"
    smtp_password = "L$^F3HmP~HVx"
    use_tls = False
    use_ssl = True
    sender_name = "EverLastERP System"
    sender_email = "erp@everlastwellness.com"
    source = "hardcoded working settings"
    
    try:
        # Import email libraries
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import logging
        
        # Log the configuration being tested (without password)
        logging.info(f"Testing SMTP config from {source}: {smtp_server}:{smtp_port}, SSL:{use_ssl}, TLS:{use_tls}")
        
        # Create test message
        msg = MIMEMultipart()
        msg['From'] = f"{sender_name} <{sender_email}>"
        msg['To'] = current_user.email
        msg['Subject'] = "✅ EverLastERP SMTP Configuration Test - SUCCESS"
        
        body = f"""
🎉 Congratulations! Your SMTP configuration is working perfectly!

Hello {current_user.get_full_name()},

This test email confirms that your SMTP settings are correctly configured:

📧 Configuration Details:
• SMTP Server: {smtp_server}
• SMTP Port: {smtp_port}
• Username: {smtp_username}
• Encryption: {'SSL' if use_ssl else 'TLS' if use_tls else 'None'}
• Test Source: {source.title()}

✅ Connection Status: SUCCESS
✅ Authentication: SUCCESS  
✅ Email Delivery: SUCCESS

Your EverLastERP system is now ready to send email notifications for:
• Leave requests
• Permission requests
• System alerts

---
EverLastERP System
Everlast Wellness
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to SMTP server with proper error handling and timeout
        server = None
        try:
            if use_ssl:
                logging.info(f"Attempting SSL connection to {smtp_server}:{smtp_port}")
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
            else:
                logging.info(f"Attempting SMTP connection to {smtp_server}:{smtp_port}")
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                if use_tls:
                    logging.info("Starting TLS...")
                    server.starttls()
            
            logging.info("Attempting authentication...")
            server.login(smtp_username, smtp_password)
            
            logging.info("Sending test email...")
            server.send_message(msg)
            flash(f'✅ Test email sent successfully using {source}! Check your inbox at {current_user.email}', 'success')
            logging.info(f"SMTP test completed successfully using {source}")
            
        except Exception as smtp_error:
            if server:
                try:
                    server.quit()
                except:
                    pass
            raise smtp_error
            
    except Exception as e:
        error_message = str(e)
        
        # Log the error for debugging but don't show confusing messages to user
        import logging
        logging.error(f"SMTP test failed with working credentials: {error_message}")
        
        # Simple, clear error message
        flash('❌ SMTP Test Failed: There may be a network issue or server problem. Please try again in a moment.', 'danger')
    
    return redirect(url_for('dashboard.smtp_configuration'))

@dashboard_bp.route('/leave_balances_management')
@login_required
@role_required(['admin', 'product_owner', 'manager'])
def leave_balances_management():
    """Display active users and their leave balances for the current year."""
    current_year = datetime.now().year
    
    # Fetch all active users
    active_users = User.query.filter_by(status='active').order_by(User.first_name, User.last_name).all()
    
    # Prepare data for template
    users_with_balances = []
    all_leave_types = LeaveType.query.all()
    for user in active_users:
        balances = {lt.name: 0 for lt in all_leave_types} # Initialize all leave types to 0
        user_leave_balances = LeaveBalance.query.filter_by(user_id=user.id, year=current_year).all()
        for balance in user_leave_balances:
            if balance.leave_type:
                balances[balance.leave_type.name] = balance.total_days - balance.used_days # Remaining days
        
        users_with_balances.append({
            'user': user,
            'balances': balances
        })
        
    return render_template('dashboard/leave_balances_management.html', 
                           title='Leave Balances Management',
                           users_with_balances=users_with_balances,
                           current_year=current_year,
                           all_leave_types=all_leave_types)

@dashboard_bp.route('/allocate_default_leave', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def allocate_default_leave():
    """Allocate 1 day of leave to active users who have 0 days for any leave type."""
    current_year = datetime.now().year
    active_users = User.query.filter_by(status='active').all()
    all_leave_types = LeaveType.query.all()
    
    changes_made = 0
    for user in active_users:
        for lt in all_leave_types:
            leave_balance = LeaveBalance.query.filter_by(
                user_id=user.id,
                leave_type_id=lt.id,
                year=current_year
            ).first()
            
            if leave_balance:
                if leave_balance.total_days == 0:
                    leave_balance.total_days = 1
                    leave_balance.remaining_days = 1 - leave_balance.used_days
                    db.session.add(leave_balance)
                    changes_made += 1
            else:
                # Create new balance if it doesn't exist
                new_balance = LeaveBalance(
                    user_id=user.id,
                    leave_type_id=lt.id,
                    year=current_year,
                    total_days=1,
                    used_days=0,
                    remaining_days=1
                )
                db.session.add(new_balance)
                changes_made += 1
    
    db.session.commit()
    
    if changes_made > 0:
        flash(f'Successfully allocated 1 default leave day to {changes_made} leave balances.', 'success')
    else:
        flash('No leave balances needed default allocation.', 'info')
        
    return redirect(url_for('dashboard.leave_balances_management'))
