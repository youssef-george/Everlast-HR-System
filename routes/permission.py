from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date, time
from forms import PermissionRequestForm, ApprovalForm
from models import PermissionRequest, User
from app import db
from helpers import role_required, create_notification, get_user_managers, get_employees_for_manager

permission_bp = Blueprint('permission', __name__, url_prefix='/permission')

@permission_bp.route('/')
@login_required
def index():
    """List permission requests based on user role"""
    user_role = current_user.role
    permission_requests = []
    
    if user_role == 'employee':
        # Employees see only their own permission requests
        permission_requests = PermissionRequest.query.filter_by(user_id=current_user.id).order_by(PermissionRequest.created_at.desc()).all()
    
    elif user_role == 'manager':
        # Managers see permission requests from their department employees
        employees = get_employees_for_manager(current_user.id)
        employee_ids = [emp.id for emp in employees]
        
        if employee_ids:
            permission_requests = PermissionRequest.query.filter(
                PermissionRequest.user_id.in_(employee_ids)
            ).order_by(PermissionRequest.created_at.desc()).all()
    
    elif user_role in ['admin', 'director']:
        # Admins and directors see all permission requests
        permission_requests = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).all()
    
    return render_template('permission/index.html', 
                           title='Permission Requests', 
                           permission_requests=permission_requests)

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
        
        # Send notifications to managers
        managers = get_user_managers(current_user)
        
        # Notify direct manager if exists
        if managers['direct_manager']:
            create_notification(
                user_id=managers['direct_manager'].id,
                message=f"New permission request from {current_user.get_full_name()} for {form.start_date.data}",
                notification_type='new_request',
                reference_id=permission_request.id,
                reference_type='permission'
            )
        
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
    
    # SPECIAL CASE: If the requester is a manager, they should bypass manager and director approval
    # and only require admin approval (implementing the new special workflow)
    requester_is_manager = requester.role == 'manager'
    
    if user_role == 'manager':
        # First, check if current user is the manager of the requester's department
        if requester.department and requester.department.manager_id == current_user.id:
            if permission_request.status == 'pending' and not permission_request.manager_approved:
                can_approve = True
                approval_form = ApprovalForm()
        # If not explicitly set as department manager, check if they're in the same dept with manager role
        elif requester.department_id and requester.department_id == current_user.department_id:
            if permission_request.status == 'pending' and not permission_request.manager_approved:
                can_approve = True
                approval_form = ApprovalForm()
    
    elif user_role == 'director':
        # Regular approval flow: Directors can approve if status is pending and manager has approved
        # EXCEPT for manager's own requests which don't need director approval
        if not requester_is_manager:
            if permission_request.status == 'pending' and permission_request.manager_approved and not permission_request.director_approved:
                can_approve = True
                approval_form = ApprovalForm()
    
    elif user_role == 'admin':
        # Get the department of the requester
        requester_department = requester.department
        
        # If requester is a manager, admins can approve directly even without manager/director approval
        if requester_is_manager:
            if permission_request.status == 'pending' and not permission_request.admin_approved:
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
        else:
            # Regular approval flow for non-manager employees
            # Admins can approve if status is pending, manager and director have approved, and request is from their department
            if permission_request.status == 'pending' and permission_request.manager_approved and permission_request.director_approved and not permission_request.admin_approved:
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
        if approval_form.status.data == 'approved':
            if user_role == 'manager':
                permission_request.manager_approved = True
                
                # For regular employees, follow the normal flow - notify directors
                if not requester_is_manager:
                    # Notify directors about the request
                    for director in get_user_managers(requester)['directors']:
                        create_notification(
                            user_id=director.id,
                            message=f"Permission request from {requester.get_full_name()} approved by manager and needs your review",
                            notification_type='approval',
                            reference_id=permission_request.id,
                            reference_type='permission'
                        )
                    
                    flash('Permission request has been approved as manager.', 'success')
                else:
                    # For manager requests, skip director approval and notify admins directly
                    all_admins = get_user_managers(requester)['admin_managers']
                    department_specific_admins = []
                    
                    # First, try to identify department-specific admins
                    if requester.department:
                        for admin in all_admins:
                            if admin.managed_department:
                                admin_managed_depts = [dept.id for dept in admin.managed_department]
                                if requester.department.id in admin_managed_depts:
                                    department_specific_admins.append(admin)
                    
                    # If no department-specific admins found, notify all admins
                    admins_to_notify = department_specific_admins if department_specific_admins else all_admins
                    
                    for admin in admins_to_notify:
                        create_notification(
                            user_id=admin.id,
                            message=f"Permission request from manager {requester.get_full_name()} needs your review",
                            notification_type='approval',
                            reference_id=permission_request.id,
                            reference_type='permission'
                        )
                    
                    flash('Permission request has been approved and sent to admin for review.', 'success')
            
            elif user_role == 'director':
                permission_request.director_approved = True
                
                # Notify relevant admins about the request
                all_admins = get_user_managers(requester)['admin_managers']
                department_specific_admins = []
                
                # First, try to identify department-specific admins
                if requester.department:
                    for admin in all_admins:
                        if admin.managed_department:
                            admin_managed_depts = [dept.id for dept in admin.managed_department]
                            if requester.department.id in admin_managed_depts:
                                department_specific_admins.append(admin)
                
                # If no department-specific admins found, notify all admins
                admins_to_notify = department_specific_admins if department_specific_admins else all_admins
                
                for admin in admins_to_notify:
                    create_notification(
                        user_id=admin.id,
                        message=f"Permission request from {requester.get_full_name()} ({requester.department.department_name if requester.department else 'No Department'}) approved by director and needs your review",
                        notification_type='approval',
                        reference_id=permission_request.id,
                        reference_type='permission'
                    )
                
                flash('Permission request has been approved as director.', 'success')
            
            elif user_role == 'admin':
                permission_request.admin_approved = True
                permission_request.status = 'approved'
                
                # If requester is a manager, auto-approve the manager and director parts for completeness
                if requester_is_manager:
                    permission_request.manager_approved = True
                    permission_request.director_approved = True
                
                # Notify the employee
                create_notification(
                    user_id=requester.id,
                    message=f"Your permission request for {permission_request.start_time.strftime('%Y-%m-%d')} has been approved",
                    notification_type='approval',
                    reference_id=permission_request.id,
                    reference_type='permission'
                )
                
                flash('Permission request has been approved.', 'success')
        
        elif approval_form.status.data == 'rejected':
            permission_request.status = 'rejected'
            
            # Notify the employee
            create_notification(
                user_id=requester.id,
                message=f"Your permission request for {permission_request.start_time.strftime('%Y-%m-%d')} has been rejected",
                notification_type='rejection',
                reference_id=permission_request.id,
                reference_type='permission'
            )
            
            flash('Permission request has been rejected.', 'warning')
        
        # Add comment if provided
        if approval_form.comment.data:
            permission_request.comment = approval_form.comment.data
            
            # Notify the employee about the comment
            create_notification(
                user_id=requester.id,
                message=f"New comment on your permission request: {approval_form.comment.data[:50]}...",
                notification_type='comment',
                reference_id=permission_request.id,
                reference_type='permission'
            )
        
        db.session.commit()
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
