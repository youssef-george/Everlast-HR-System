from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date, time
from forms import PermissionRequestForm, ApprovalForm, AdminPermissionRequestForm
from models import db, PermissionRequest, User
from helpers import role_required, get_user_managers, get_employees_for_manager, send_admin_email_notification
import logging

permission_bp = Blueprint('permission', __name__, url_prefix='/permission')

@permission_bp.route('/')
@login_required
def index():
    """List permission requests based on user role and view parameter"""
    user_role = current_user.role
    permission_requests = []
    view_type = request.args.get('view', None)  # Get the view parameter from URL
    page_title = 'Permission Requests'
    
    if user_role == 'employee':
        # Employees see only their own permission requests
        permission_requests = PermissionRequest.query.filter_by(user_id=current_user.id).order_by(PermissionRequest.created_at.desc()).all()
    
    elif user_role == 'manager':
        if view_type == 'my':
            # Show only the manager's own requests
            page_title = 'My Permission Requests'
            permission_requests = PermissionRequest.query.filter_by(user_id=current_user.id).order_by(PermissionRequest.created_at.desc()).all()
        else:
            # Show team requests (default view for managers)
            page_title = 'Team Permission Requests'
            employees = get_employees_for_manager(current_user.id)
            employee_ids = [emp.id for emp in employees]
            
            if employee_ids:
                permission_requests = PermissionRequest.query.filter(
                    PermissionRequest.user_id.in_(employee_ids)
                ).order_by(PermissionRequest.created_at.desc()).all()
    
    elif user_role in ['admin', 'product_owner']:
        # Admins and Product Owners see all permission requests from their departments, if assigned
        if current_user.managed_department:
            # If admin/product_owner is assigned to specific departments, show only requests from those departments
            admin_dept_ids = [dept.id for dept in current_user.managed_department]
            permission_requests = PermissionRequest.query.join(User).filter(
                User.department_id.in_(admin_dept_ids)
            ).order_by(PermissionRequest.created_at.desc()).all()
        else:
            # If admin/product_owner is not assigned to specific departments, show all requests
            permission_requests = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).all()
    
    elif user_role == 'director':
        # Directors see all permission requests
        page_title = 'All Company Permission Requests'
        permission_requests = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).all()
    
    # Get departments for filtering (for admin and director roles)
    departments = []
    if user_role in ['admin', 'director']:
        from models import Department
        departments = Department.query.all()
    
    return render_template('permission/index.html', 
                           title=page_title, 
                           permission_requests=permission_requests,
                           view_type=view_type,
                           departments=departments)

@permission_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new permission request"""
    form = PermissionRequestForm()
    
    if form.validate_on_submit():
        # Combine date and time
        start_datetime = datetime.combine(form.start_date.data, form.start_time.data)
        end_datetime = datetime.combine(form.start_date.data, form.end_time.data)
        
        # Allow selecting the previous day
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        
        if start_datetime.date() < yesterday:
            flash('Permission requests can only be for yesterday, today, or future dates.', 'danger')
            return render_template('permission/create.html', title='Create Permission Request', form=form)
        
        permission_request = PermissionRequest(
            user_id=current_user.id,
            start_time=start_datetime,
            end_time=end_datetime,
            reason=form.reason.data,
            status='pending'
        )
        
        db.session.add(permission_request)
        db.session.commit()
        
        # Send email notification to admins
        try:
            employee_name = current_user.get_full_name()
            start_date = form.start_date.data.strftime('%B %d, %Y')
            start_time = form.start_time.data.strftime('%I:%M %p')
            end_time = form.end_time.data.strftime('%I:%M %p')
            duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
            
            subject = f"New Permission Request - {employee_name}"
            message = f"""
            A new permission request has been submitted and requires your review:
            
            <strong>Employee:</strong> {employee_name}<br>
            <strong>Date:</strong> {start_date}<br>
            <strong>Time:</strong> {start_time} - {end_time}<br>
            <strong>Duration:</strong> {duration_hours:.1f} hour(s)<br>
            <strong>Reason:</strong> {form.reason.data}<br>
            """
            
            send_admin_email_notification(subject, message, "permission", permission_request.id)
        except Exception as e:
            logging.error(f"Failed to send admin email notification: {str(e)}")
        
        flash('Your permission request has been submitted successfully!', 'success')
        return redirect(url_for('permission.index'))
    
    return render_template('permission/create.html', 
                           title='Create Permission Request', 
                           form=form)

@permission_bp.route('/view/<int:id>', methods=['GET', 'POST'])
@login_required
def view(id):
    """View a permission request with the option to approve/reject based on role"""
    permission_request = PermissionRequest.query.get_or_404(id)
    
    # Check if user has permission to view this request
    user_role = current_user.role
    if user_role == 'employee' and permission_request.user_id != current_user.id:
        flash('You do not have permission to view this permission request.', 'danger')
        return redirect(url_for('permission.index'))
    
    # Get the requester's information
    requester = User.query.get(permission_request.user_id)
    
    # Determine if current user can approve this request
    can_approve = False
    approval_form = None
    
    # SIMPLIFIED WORKFLOW: Only admin approval required for all permission requests
    if user_role == 'admin':
        # Get the department of the requester
        requester_department = requester.department
        
        # Admins can approve any pending permission request
        if permission_request.status == 'pending' and permission_request.admin_status != 'approved':
            # If the admin is specifically assigned to handle a department
            if current_user.managed_department:
                # Check if the requester is from a department this admin manages
                admin_managed_departments = [dept.id for dept in current_user.managed_department]
                if requester_department and requester_department.id in admin_managed_departments:
                    can_approve = True
                    approval_form = ApprovalForm()
            else:
                # If admin is not assigned to any specific department, they can approve any department
                can_approve = True
                approval_form = ApprovalForm()
    
    # Handle approval/rejection submission
    if approval_form and approval_form.validate_on_submit():
        approval_status = approval_form.status.data
        comment = approval_form.comment.data
        
        if user_role == 'admin':
            permission_request.admin_status = approval_status
            permission_request.admin_comment = comment
            permission_request.admin_updated_at = datetime.utcnow()
            
            # Update overall status
            permission_request.update_overall_status()
            
            # User notification removed - will be replaced with SMTP email notifications
            
            db.session.commit()
            flash(f'Permission request has been {approval_status}.', 'success')
            return redirect(url_for('permission.index'))
    
    return render_template('permission/view.html',
                           title='View Permission Request',
                           permission_request=permission_request,
                           requester=requester,
                           can_approve=can_approve,
                           approval_form=approval_form)

@permission_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit a permission request (only if it's still pending and belongs to current user)"""
    permission_request = PermissionRequest.query.get_or_404(id)
    
    # Check if user can edit this request
    if permission_request.user_id != current_user.id:
        flash('You can only edit your own permission requests.', 'danger')
        return redirect(url_for('permission.index'))
    
    if permission_request.status != 'pending':
        flash('You can only edit pending permission requests.', 'danger')
        return redirect(url_for('permission.index'))
    
    # Prepare form with existing data
    form = PermissionRequestForm()
    
    if request.method == 'GET':
        form.start_date.data = permission_request.start_time.date()
        form.start_time.data = permission_request.start_time.time()
        form.end_time.data = permission_request.end_time.time()
        form.reason.data = permission_request.reason
    
    if form.validate_on_submit():
        # Combine date and time
        start_datetime = datetime.combine(form.start_date.data, form.start_time.data)
        end_datetime = datetime.combine(form.start_date.data, form.end_time.data)
        
        # Allow selecting the previous day
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        
        if start_datetime.date() < yesterday:
            flash('Permission requests can only be for yesterday, today, or future dates.', 'danger')
            return render_template('permission/create.html', title='Edit Permission Request', form=form, is_edit=True)
        
        permission_request.start_time = start_datetime
        permission_request.end_time = end_datetime
        permission_request.reason = form.reason.data
        
        db.session.commit()
        
        flash('Your permission request has been updated successfully!', 'success')
        return redirect(url_for('permission.index'))
    
    return render_template('permission/create.html',
                          title='Edit Permission Request',
                          form=form,
                          is_edit=True)

@permission_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    """Delete a permission request (only if it's still pending and belongs to current user)"""
    permission_request = PermissionRequest.query.get_or_404(id)
    
    # Check if user can delete this request
    if permission_request.user_id != current_user.id:
        flash('You can only delete your own permission requests.', 'danger')
        return redirect(url_for('permission.index'))
    
    if permission_request.status != 'pending':
        flash('You can only delete pending permission requests.', 'danger')
        return redirect(url_for('permission.index'))
    
    db.session.delete(permission_request)
    db.session.commit()
    
    flash('Your permission request has been deleted successfully!', 'success')
    return redirect(url_for('permission.index'))


@permission_bp.route('/admin-create', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner', 'manager'])
def admin_create():
    """Allow admin to create permission requests on behalf of employees"""
    form = AdminPermissionRequestForm()
    
    # Populate employee dropdown with active employees (excluding test users)
    if current_user.role == 'manager':
        # Managers see only employees in their department or who report to them
        # Get employees in the manager's department
        department_employees = User.query.filter(
            User.status == 'active',
            User.department_id == current_user.department_id,
            User.id != current_user.id,  # Exclude the manager themselves
            ~User.first_name.like('User%'),
            ~User.first_name.like('NN-%'),
            User.first_name != '',
            User.last_name != ''
        )

        # Get employees who report directly to the manager
        reporting_employees = User.query.filter(
            User.status == 'active',
            User.manager_id == current_user.id,
            User.id != current_user.id,  # Exclude the manager themselves
            ~User.first_name.like('User%'),
            ~User.first_name.like('NN-%'),
            User.first_name != '',
            User.last_name != ''
        )
        
        # Combine and get unique employees
        employees = department_employees.union(reporting_employees).order_by(User.first_name).all()

    elif current_user.managed_department:
        # If admin/product_owner is assigned to specific departments, show only employees from those departments
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        employees = User.query.filter(
            User.status == 'active',
            User.department_id.in_(admin_dept_ids),
            ~User.first_name.like('User%'),  # Exclude generic test users
            ~User.first_name.like('NN-%'),   # Exclude numbered test users
            User.first_name != '',           # Exclude empty names
            User.last_name != ''             # Exclude users without last names
        ).order_by(User.first_name).all()
    else:
        # If admin/product_owner is not assigned to specific departments, show all active employees
        employees = User.query.filter(
            User.status == 'active',
            ~User.first_name.like('User%'),  # Exclude generic test users
            ~User.first_name.like('NN-%'),   # Exclude numbered test users
            User.first_name != '',           # Exclude empty names
            User.last_name != ''             # Exclude users without last names
        ).order_by(User.first_name).all()

    # Create choices list for the dropdown: [(id, "First Last (Department)")]
    employee_choices = []
    for employee in employees:
        dept_name = employee.department.department_name if employee.department else "No Department"
        display_text = f"{employee.get_full_name()} ({dept_name})"
        employee_choices.append((employee.id, display_text))
    
    form.employee_id.choices = employee_choices
    
    if form.validate_on_submit():
        # Get the selected employee
        employee = User.query.get(form.employee_id.data)
        
        if not employee:
            flash('Selected employee does not exist.', 'danger')
            return redirect(url_for('permission.admin_create'))
        
        # Validate if the manager is authorized to submit for this employee
        if current_user.role == 'manager':
            # Check if the selected employee is in the manager's department or reports to them
            is_in_department = (employee.department_id == current_user.department_id)
            is_direct_report = (employee.manager_id == current_user.id)

            if not (is_in_department or is_direct_report):
                flash('You can only submit requests for your team members.', 'danger')
                return redirect(url_for('permission.admin_create'))
        
        # Combine date and time
        start_datetime = datetime.combine(form.start_date.data, form.start_time.data)
        end_datetime = datetime.combine(form.start_date.data, form.end_time.data)
        
        # Allow selecting the previous day
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        
        if start_datetime.date() < yesterday:
            flash('Permission requests can only be for yesterday, today, or future dates.', 'danger')
            return render_template('permission/admin_create.html', title='Create Permission Request for Employee', form=form)
        
        # Create the permission request for the employee
        permission_request = PermissionRequest(
            user_id=employee.id,
            start_time=start_datetime,
            end_time=end_datetime,
            reason=form.reason.data,
            status='pending'
        )
        
        # If the employee is a manager, no special handling needed since only admin approval is required
        
        db.session.add(permission_request)
        db.session.commit()
        
        # Employee notification removed - will be replaced with SMTP email notifications
        
        # Manager and director notifications removed - will be replaced with SMTP email notifications
        
        flash(f'Permission request for {employee.get_full_name()} has been submitted successfully!', 'success')
        return redirect(url_for('permission.index'))
    
    return render_template('permission/admin_create.html', 
                          title='Create Permission Request for Employee', 
                          form=form)
