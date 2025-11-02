from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, make_response, send_file, Response
from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from models import User, LeaveRequest, PermissionRequest, DailyAttendance, Department
from helpers import role_required, get_dashboard_stats
from forms import UserEditForm # Assuming UserEditForm is defined in forms.py
import io
import csv
import xlsxwriter

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
    from helpers import leave_request_to_dict, permission_request_to_dict
    
    stats = get_dashboard_stats(current_user)
    
    # Get the user's leave and permission requests
    leave_requests_db = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    permission_requests_db = PermissionRequest.query.filter_by(user_id=current_user.id).order_by(PermissionRequest.created_at.desc()).limit(5).all()
    
    # Convert to JSON-serializable format for chart data
    leave_requests_json = [leave_request_to_dict(lr) for lr in leave_requests_db]
    permission_requests_json = [permission_request_to_dict(pr) for pr in permission_requests_db]
    
    return render_template('dashboard/employee.html', 
                           title='Employee Dashboard',
                           stats=stats,
                           leave_requests=leave_requests_json,
                           permission_requests=permission_requests_json,
                           leave_requests_db=leave_requests_db,
                           permission_requests_db=permission_requests_db)

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
            
            # Get permission requests needing manager approval
            permission_requests = PermissionRequest.query.filter_by(
                user_id=employee.id,
                status='pending',
                manager_status='pending'
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
    
    return render_template('dashboard/manager.html',
                          title='Manager Dashboard',
                          stats=stats,
                          employees=employees,
                          pending_leave_requests=pending_leave_requests[:5],
                          pending_permission_requests=pending_permission_requests[:5],
                          personal_leave_requests=personal_leave_requests,
                          personal_permission_requests=personal_permission_requests)

@dashboard_bp.route('/admin')
@login_required
@role_required('admin')
def admin():
    """Admin dashboard showing all company data and analytics"""
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
    # All admins now see all users, regardless of department assignments
    # Get all users, both active and inactive, sorted by fingerprint number
    # Treat None or missing fingerprint numbers as 0 for sorting purposes
    all_users = User.query.all()
    all_users.sort(key=lambda user: int(user.fingerprint_number) if user.fingerprint_number is not None and (isinstance(user.fingerprint_number, int) or (isinstance(user.fingerprint_number, str) and user.fingerprint_number.isdigit())) else 0)
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
    
    # Admins now have full access to all users regardless of department
    # No need to check for department-specific permissions
    
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
    
    # Admins now have full access to all users regardless of department
    # No need to check for department-specific permissions
    
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
    
    # All admins now have access to all departments
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
        user.avaya_number = form.avaya_number.data if form.avaya_number.data else None
        user.fingerprint_number = form.fingerprint_number.data if form.fingerprint_number.data else None
        user.avaya_number = form.avaya_number.data if form.avaya_number.data else None
        user.role = form.role.data
        user.status = form.status.data
        user.joining_date = form.joining_date.data
        
        # Handle department selection
        if form.department_id.data == 0:
            user.department_id = None
        else:
            user.department_id = form.department_id.data
            
        # Update password if provided
        if form.new_password.data:
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(form.new_password.data)
            
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
def members():
    """Page showing all active and inactive members in the system"""
    # All users can see all active members, regardless of role
    # Get all active users ordered by last name
    # Get all active users, sorted by department name, then by last name and first name
    active_users = User.query.filter_by(status='active').all()
    inactive_users = User.query.filter_by(status='inactive').all()
    print(f"Active users fetched: {len(active_users)}")
    for user in active_users:
        print(f"    - {user.first_name} {user.last_name}, Role: {user.role}, Department: {user.department.department_name if user.department else 'N/A'}, Status: {user.status}")
    print(f"Inactive users fetched: {len(inactive_users)}")
    for user in inactive_users:
        print(f"    - {user.first_name} {user.last_name}, Role: {user.role}, Department: {user.department.department_name if user.department else 'N/A'}, Status: {user.status}")

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
    inactive_users = sort_users_by_department(inactive_users)
    # Get all departments for filtering
    departments = Department.query.all()
    
    return render_template('dashboard/members.html', title='Company Members', active_users=active_users, inactive_users=inactive_users, departments=departments)


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

@dashboard_bp.route('/director')
@login_required
@role_required('director')
def director():
    """Director dashboard focusing on permission requests approval"""
    stats = get_dashboard_stats(current_user)
    
    # For directors, we'll show all department requests, but we could limit to specific
    # departments if the director has specific department responsibilities in the future
    pending_permission_requests = PermissionRequest.query.filter_by(
        status='pending',
        manager_status='approved',
        director_status='pending'
    ).order_by(PermissionRequest.created_at.desc()).limit(10).all()
    
    # Get recent activity
    recent_permissions = PermissionRequest.query.order_by(PermissionRequest.updated_at.desc()).limit(5).all()
    
    return render_template('dashboard/director.html',
                          title='Director Dashboard',
                          stats=stats,
                          pending_permission_requests=pending_permission_requests,
                          recent_permissions=recent_permissions)

@dashboard_bp.route('/search_users', methods=['GET'])
@login_required
@role_required(['Admin', 'HR', 'Manager'])
def search_users():
    query = request.args.get('query', '').strip()
    users = []
    if query:
        # Search by first name, last name, fingerprint number, or department name
        users_query = User.query.join(Department, User.department_id == Department.id, isouter=True).filter(
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

@dashboard_bp.route('/report', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hr', 'manager')
def report():
    query = request.args.get('query', '').strip()
    
    base_query = User.query

    if current_user.role == 'Manager':
        base_query = base_query.filter_by(department_id=current_user.department_id)
    else:
        base_query = base_query.filter_by(status='active')

    if query:
        # Apply search filter if query is present
        base_query = base_query.join(Department, User.department_id == Department.id, isouter=True).filter(
            (User.first_name.ilike(f'%{query}%')) |
            (User.last_name.ilike(f'%{query}%')) |
            (User.fingerprint_number.ilike(f'%{query}%')) |
            (Department.department_name.ilike(f'%{query}%'))
        )

    users = base_query.order_by(User.first_name).all()
    selected_user = None
    start_date = None
    end_date = None
    report_data = None
    summary_metrics = None
    all_user_reports = [] # Initialize here

    if request.method == 'POST':
        user_ids = request.form.getlist('user_id')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        selected_users = []
        if user_ids:
            for uid in user_ids:
                if uid and uid != '0':
                    user = User.query.get(uid)
                    if user:
                        selected_users.append(user)

        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            for user in selected_users:
                report_data = []
                total_days = 0
                present_days = 0
                absent_days = 0
                leave_days = 0
                permission_days = 0
                day_off_days = 0
                extra_time_hours = 0.0

                current_date = start_date
                while current_date <= end_date:
                    total_days += 1
                    day_of_week = current_date.strftime('%A')
                    status = 'Absent'
                    check_in = None
                    check_out = None
                    hours_worked = 0.0

                    # Check if before joining date
                    if current_date < user.joining_date:
                        status = 'Not Yet Joined'
                    else:
                        # Check for day off
                        if current_date.weekday() in [4, 5]:  # Friday (4) or Saturday (5)
                            attendance = DailyAttendance.query.filter_by(user_id=user.id, date=current_date).first()
                            if attendance and attendance.first_check_in and attendance.last_check_out:
                                status = 'Day Off / Present'
                                present_days += 1
                                check_in = attendance.first_check_in
                                check_out = attendance.last_check_out
                                if check_in and check_out:
                                    time_diff = datetime.combine(current_date, check_out.time()) - datetime.combine(current_date, check_in.time())
                                    hours_worked = time_diff.total_seconds() / 3600
                                    if hours_worked > 9:
                                        extra_time_hours += (hours_worked - 9)
                            else:
                                status = 'Day Off'
                            day_off_days += 1
                        else:
                            # Check for leave requests
                            leave_request = LeaveRequest.query.filter(
                                LeaveRequest.user_id == user.id,
                                LeaveRequest.start_date <= current_date,
                                LeaveRequest.end_date >= current_date,
                                LeaveRequest.status == 'approved'
                            ).first()

                            if leave_request:
                                status = 'Leave'
                                leave_days += 1
                            else:
                                # Check for permission requests
                                permission_request = PermissionRequest.query.filter(
                                    PermissionRequest.user_id == user.id,
                                    PermissionRequest.start_time <= current_date,
                                    PermissionRequest.end_time >= current_date,
                                    PermissionRequest.status == 'approved'
                                ).first()

                                if permission_request:
                                    status = 'Permission'
                                    permission_days += 1
                                else:
                                    # Check daily attendance
                                    attendance = DailyAttendance.query.filter_by(user_id=user.id, date=current_date).first()
                                    if attendance:
                                        status = 'Present'
                                        present_days += 1
                                        check_in = attendance.first_check_in
                                        check_out = attendance.last_check_out
                                        if check_in and check_out:
                                             time_diff = datetime.combine(current_date, check_out.time()) - datetime.combine(current_date, check_in.time())
                                             hours_worked = time_diff.total_seconds() / 3600
                                             if hours_worked > 9:
                                                extra_time_hours += (hours_worked - 9)
                                    else:
                                        absent_days += 1

                    report_data.append({
                        'date': current_date,
                        'day_of_week': day_of_week,
                        'status': status,
                        'check_in': check_in,
                        'check_out': check_out,
                        'hours_worked': hours_worked
                    })
                    current_date += timedelta(days=1)

                summary_metrics = {
                    'total_days': total_days,
                    'present_days': present_days,
                    'absent_days': absent_days,
                    'leave_days': leave_days,
                    'permission_days': permission_days,
                    'day_off_days': day_off_days,
                    'extra_time_hours': round(extra_time_hours, 2)
                }
                all_user_reports.append({
                    'user': user,
                    'summary_metrics': summary_metrics,
                    'report_data': report_data
                })
    return render_template('dashboard/report.html', users=users, selected_user=selected_user, start_date=start_date, end_date=end_date, all_user_reports=all_user_reports)








@dashboard_bp.route('/export_report/<int:user_id>/<string:start_date>/<string:end_date>/<string:format>', methods=['GET'])
@login_required
@role_required('admin', 'hr', 'manager')
def export_report(user_id, start_date, end_date, format):
    user = User.query.get(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard.report'))

    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    report_data = []
    total_days = 0
    present_days = 0
    absent_days = 0
    leave_days = 0
    permission_days = 0
    day_off_days = 0
    extra_time_hours = 0.0

    current_date = start_date
    while current_date <= end_date:
        total_days += 1
        day_of_week = current_date.strftime('%A')
        status = 'Absent'
        check_in = None
        check_out = None
        hours_worked = 0.0

        # Check if before joining date
        if current_date < user.joining_date:
            status = 'Not Yet Joined'
        else:
            # Check for day off
            if current_date.weekday() in [5, 6]:  # Saturday (5) or Sunday (6)
                status = 'Day Off'
                day_off_days += 1
            else:
                # Check for leave requests
                leave_request = LeaveRequest.query.filter(
                    LeaveRequest.user_id == user.id,
                    LeaveRequest.start_date <= current_date,
                    LeaveRequest.end_date >= current_date,
                    LeaveRequest.status == 'approved'
                ).first()

                if leave_request:
                    status = 'Leave'
                    leave_days += 1
                else:
                    # Check for permission requests
                    permission_request = PermissionRequest.query.filter(
                        PermissionRequest.user_id == user.id,
                        PermissionRequest.start_time <= current_date,
                        PermissionRequest.end_time >= current_date,
                        PermissionRequest.status == 'approved'
                    ).first()

                    if permission_request:
                        status = 'Permission'
                        permission_days += 1
                    else:
                        # Check daily attendance
                        attendance = DailyAttendance.query.filter_by(user_id=user.id, date=current_date).first()
                        if attendance:
                            status = 'Present'
                            present_days += 1
                            check_in = attendance.check_in
                            check_out = attendance.check_out
                            if check_in and check_out:
                                time_diff = datetime.combine(current_date, check_out) - datetime.combine(current_date, check_in)
                                hours_worked = time_diff.total_seconds() / 3600
                                if hours_worked > 9:
                                    extra_time_hours += (hours_worked - 9)
                        else:
                            absent_days += 1

        report_data.append({
            'date': current_date,
            'day_of_week': day_of_week,
            'status': status,
            'check_in': check_in,
            'check_out': check_out,
            'hours_worked': hours_worked
        })
        current_date += timedelta(days=1)

    summary_metrics = {
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': absent_days,
        'leave_days': leave_days,
        'permission_days': permission_days,
        'day_off_days': day_off_days,
        'extra_time_hours': round(extra_time_hours, 2)
    }

    # Export logic based on format
    if format == 'pdf':
        # For PDF, we'll render an HTML template and convert it to PDF
        rendered_html = render_template('dashboard/report_export.html', user=user, summary_metrics=summary_metrics, report_data=report_data, start_date=start_date, end_date=end_date)
        # You would typically use a library like WeasyPrint or xhtml2pdf here
        # For demonstration, we'll just return the HTML as a response
        # In a real application, you'd convert rendered_html to PDF bytes and return as send_file
        response = make_response(rendered_html)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_report_{user.first_name}_{user.last_name}.pdf'
        return response
    elif format == 'excel':
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet()

        # Write employee info
        worksheet.write('A1', 'Employee Name:')
        worksheet.write('B1', f'{user.first_name} {user.last_name}')
        worksheet.write('A2', 'Email:')
        worksheet.write('B2', user.email)
        worksheet.write('A3', 'Fingerprint Number:')
        worksheet.write('B3', user.fingerprint_number)
        worksheet.write('A4', 'Date Range:')
        worksheet.write('B4', f'{start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}')

        # Write summary metrics
        row_offset = 6
        worksheet.write(row_offset, 0, 'Summary Metrics')
        worksheet.write(row_offset + 1, 0, 'Total Days:')
        worksheet.write(row_offset + 1, 1, summary_metrics['total_days'])
        worksheet.write(row_offset + 2, 0, 'Present Days:')
        worksheet.write(row_offset + 2, 1, summary_metrics['present_days'])
        worksheet.write(row_offset + 3, 0, 'Absent Days:')
        worksheet.write(row_offset + 3, 1, summary_metrics['absent_days'])
        worksheet.write(row_offset + 4, 0, 'Leave Days:')
        worksheet.write(row_offset + 4, 1, summary_metrics['leave_days'])
        worksheet.write(row_offset + 5, 0, 'Permission Days:')
        worksheet.write(row_offset + 5, 1, summary_metrics['permission_days'])
        worksheet.write(row_offset + 6, 0, 'Day Off Days:')
        worksheet.write(row_offset + 6, 1, summary_metrics['day_off_days'])
        worksheet.write(row_offset + 7, 0, 'Extra Time (hours):')
        worksheet.write(row_offset + 7, 1, summary_metrics['extra_time_hours'])

        # Write detailed breakdown headers
        row_offset += 10
        worksheet.write(row_offset, 0, 'Date')
        worksheet.write(row_offset, 1, 'Day')
        worksheet.write(row_offset, 2, 'Status')
        worksheet.write(row_offset, 3, 'Check-in')
        worksheet.write(row_offset, 4, 'Check-out')
        worksheet.write(row_offset, 5, 'Hours Worked')

        # Write detailed breakdown data
        for i, record in enumerate(report_data):
            worksheet.write(row_offset + i + 1, 0, record['date'].strftime('%Y-%m-%d'))
            worksheet.write(row_offset + i + 1, 1, record['day_of_week'])
            worksheet.write(row_offset + i + 1, 2, record['status'])
            worksheet.write(row_offset + i + 1, 3, record['check_in'].strftime('%H:%M:%S') if record['check_in'] else 'N/A')
            worksheet.write(row_offset + i + 1, 4, record['check_out'].strftime('%H:%M:%S') if record['check_out'] else 'N/A')
            worksheet.write(row_offset + i + 1, 5, record['hours_worked'])

        workbook.close()
        output.seek(0)

        return send_file(output, download_name=f'attendance_report_{user.first_name}_{user.last_name}.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    elif format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)

        # Write employee info
        writer.writerow(['Employee Name:', f'{user.first_name} {user.last_name}'])
        writer.writerow(['Email:', user.email])
        writer.writerow(['Fingerprint Number:', user.fingerprint_number])
        writer.writerow(['Date Range:', f'{start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}', ''])

        writer.writerow([])

        # Write summary metrics
        writer.writerow(['Summary Metrics'])
        writer.writerow(['Total Days:', summary_metrics['total_days']])
        writer.writerow(['Present Days:', summary_metrics['present_days']])
        writer.writerow(['Absent Days:', summary_metrics['absent_days']])
        writer.writerow(['Leave Days:', summary_metrics['leave_days']])
        writer.writerow(['Permission Days:', summary_metrics['permission_days']])
        writer.writerow(['Day Off Days:', summary_metrics['day_off_days']])
        writer.writerow(['Extra Time (hours):', summary_metrics['extra_time_hours']])
        writer.writerow([])

        # Write detailed breakdown headers
        writer.writerow(['Date', 'Day', 'Status', 'Check-in', 'Check-out', 'Hours Worked'])

        # Write detailed breakdown data
        for record in report_data:
            writer.writerow([
                record['date'].strftime('%Y-%m-%d'),
                record['day_of_week'],
                record['status'],
                record['check_in'].strftime('%H:%M:%S') if record['check_in'] else 'N/A',
                record['check_out'].strftime('%H:%M:%S') if record['check_out'] else 'N/A',
                record['hours_worked']
            ])

        output.seek(0)
        return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment;filename=attendance_report_{user.first_name}_{user.last_name}.csv'})
    else:
        flash('Invalid export format.', 'danger')
        return redirect(url_for('dashboard.report'))

@dashboard_bp.route('/search_employees_ajax', methods=['GET'])
@login_required
@role_required('admin', 'hr', 'manager')
def search_employees_ajax():
    query = request.args.get('query', '')
    page = request.args.get('page', type=int, default=1)
    
    # Base query for active users
    users_query = User.query.filter_by(status='active')

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
