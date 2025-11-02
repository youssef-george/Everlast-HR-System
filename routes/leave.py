from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date
from forms import LeaveRequestForm, ApprovalForm, AdminLeaveRequestForm
from models import db, LeaveRequest, User
from helpers import role_required, create_notification, get_user_managers, get_employees_for_manager

leave_bp = Blueprint('leave', __name__, url_prefix='/leave')

@leave_bp.route('/')
@login_required
def index():
    """List leave requests based on user role and view parameter"""
    user_role = current_user.role
    leave_requests = []
    view_type = request.args.get('view', None)  # Get the view parameter from URL
    page_title = 'Leave Requests'
    
    if user_role == 'employee':
        # Employees see only their own leave requests
        leave_requests = LeaveRequest.query.filter_by(
            user_id=current_user.id
        ).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'manager':
        if view_type == 'my':
            # Show only the manager's own requests
            page_title = 'My Leave Requests'
            leave_requests = LeaveRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(LeaveRequest.created_at.desc()).all()
        else:
            # Show team requests (default view for managers)
            page_title = 'Team Leave Requests'
            # Get employees from all departments managed by this manager
            managed_dept_ids = [dept.id for dept in current_user.managed_department]
            if managed_dept_ids:
                leave_requests = LeaveRequest.query.join(User).filter(
                    User.department_id.in_(managed_dept_ids),
                    LeaveRequest.user_id != current_user.id  # Exclude manager's own requests
                ).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'admin':
        if view_type == 'my':
            page_title = 'My Leave Requests'
            leave_requests = LeaveRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(LeaveRequest.created_at.desc()).all()
        elif view_type == 'all':
            page_title = 'All Leave Requests'
            # Show all requests if explicitly requested
            leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
        else:
            page_title = 'Leave Requests for Approval'
            # Get requests that need admin approval based on department assignments
            if current_user.managed_department:
                admin_dept_ids = [dept.id for dept in current_user.managed_department]
                leave_requests = LeaveRequest.query.join(User).filter(
                    LeaveRequest.manager_status == 'approved',
                    LeaveRequest.admin_status == 'pending',
                    User.department_id.in_(admin_dept_ids)
                ).order_by(LeaveRequest.created_at.desc()).all()
            else:
                # If not assigned to specific departments, show all pending admin approvals
                leave_requests = LeaveRequest.query.filter_by(
                    manager_status='approved',
                    admin_status='pending'
                ).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'general_manager':
        if view_type == 'my':
            page_title = 'My Leave Requests'
            leave_requests = LeaveRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(LeaveRequest.created_at.desc()).all()
        elif view_type == 'all':
            page_title = 'All Leave Requests'
            leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
        else:
            page_title = 'Leave Requests for Final Approval'
            leave_requests = LeaveRequest.query.filter_by(
                manager_status='approved',
                admin_status='approved',
                general_manager_status='pending'
            ).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'director':
        # Directors see all leave requests
        leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    
    # Add pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    leave_requests_paginated = leave_requests[(page-1)*per_page:page*per_page]
    total_pages = (len(leave_requests) + per_page - 1) // per_page
    
    return render_template('leave/index.html', 
                         title=page_title, 
                         leave_requests=leave_requests_paginated,
                         view_type=view_type,
                         total_pages=total_pages,
                         current_page=page,
                         total_records=len(leave_requests))

@leave_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new leave request"""
    form = LeaveRequestForm()
    
    if form.validate_on_submit():
        leave_request = LeaveRequest(
            user_id=current_user.id,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            reason=form.reason.data,
            status='pending'
        )
        
        db.session.add(leave_request)
        db.session.commit()
        
        # Send notifications to managers
        managers = get_user_managers(current_user)
        
        # Notify direct manager if exists
        if managers['direct_manager']:
            create_notification(
                user_id=managers['direct_manager'].id,
                message=f"New leave request from {current_user.get_full_name()} from {form.start_date.data} to {form.end_date.data}",
                notification_type='new_request',
                reference_id=leave_request.id,
                reference_type='leave'
            )
        
        flash('Your leave request has been submitted successfully!', 'success')
        return redirect(url_for('leave.index'))
    
    return render_template('leave/create.html', 
                           title='Create Leave Request', 
                           form=form)

@leave_bp.route('/view/<int:id>', methods=['GET', 'POST'])
@login_required
def view(id):
    """View a leave request with the option to approve/reject based on role"""
    leave_request = LeaveRequest.query.get_or_404(id)
    
    # Check if user has permission to view this request
    user_role = current_user.role
    if user_role == 'employee' and leave_request.user_id != current_user.id:
        flash('You do not have permission to view this leave request.', 'danger')
        return redirect(url_for('leave.index'))
    
    # Get the requester's information
    requester = User.query.get(leave_request.user_id)
    
    # Determine if current user can approve this request
    can_approve = False
    approval_form = None
    
    if user_role == 'manager':
        # Manager can approve if they are the department manager and request is pending manager approval
        if (requester.department and requester.department.manager_id == current_user.id and 
            leave_request.manager_status == 'pending'):
            can_approve = True
            approval_form = ApprovalForm()
    
    elif user_role == 'admin':
        # Admin can approve if request has manager approval and is pending admin approval
        if (leave_request.manager_status == 'approved' and 
            leave_request.admin_status == 'pending'):
            can_approve = True
            approval_form = ApprovalForm()
    
    elif user_role == 'general_manager':
        # General Manager can approve if request has both manager and admin approval
        if (leave_request.manager_status == 'approved' and 
            leave_request.admin_status == 'approved' and 
            leave_request.general_manager_status == 'pending'):
            can_approve = True
            approval_form = ApprovalForm()
    
    # Handle approval/rejection submission
    if approval_form and approval_form.validate_on_submit():
        approval_status = approval_form.status.data
        comment = approval_form.comment.data
        
        if user_role == 'manager':
            leave_request.manager_status = approval_status
            leave_request.manager_comment = comment
            leave_request.manager_updated_at = datetime.utcnow()
            
            if approval_status == 'approved':
                # Notify admins
                admins = User.query.filter_by(role='admin').all()
                for admin in admins:
                    create_notification(
                        user_id=admin.id,
                        message=f"Leave request from {requester.get_full_name()} needs admin review",
                        notification_type='approval_needed',
                        reference_id=leave_request.id,
                        reference_type='leave'
                    )
        
        elif user_role == 'admin':
            leave_request.admin_status = approval_status
            leave_request.admin_comment = comment
            leave_request.admin_updated_at = datetime.utcnow()
            
            if approval_status == 'approved':
                # Notify general managers
                general_managers = User.query.filter_by(role='general_manager').all()
                for gm in general_managers:
                    create_notification(
                        user_id=gm.id,
                        message=f"Leave request from {requester.get_full_name()} needs final approval",
                        notification_type='approval_needed',
                        reference_id=leave_request.id,
                        reference_type='leave'
                    )
        
        elif user_role == 'general_manager':
            leave_request.general_manager_status = approval_status
            leave_request.general_manager_comment = comment
            leave_request.general_manager_updated_at = datetime.utcnow()
        
        # Update overall status
        leave_request.update_overall_status()
        
        # Notify the requester
        create_notification(
            user_id=requester.id,
            message=f"Your leave request has been {approval_status} by {user_role.replace('_', ' ').title()}",
            notification_type='status_update',
            reference_id=leave_request.id,
            reference_type='leave'
        )
        
        db.session.commit()
        flash(f'Leave request has been {approval_status}.', 'success')
        return redirect(url_for('leave.index'))
    
    return render_template('leave/view.html',
                           title='View Leave Request',
                           leave_request=leave_request,
                           requester=requester,
                           can_approve=can_approve,
                           approval_form=approval_form)

@leave_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit a leave request (only if it's still pending and belongs to current user)"""
    leave_request = LeaveRequest.query.get_or_404(id)
    
    # Check if user can edit this request
    if leave_request.user_id != current_user.id:
        flash('You can only edit your own leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    if leave_request.status != 'pending':
        flash('You can only edit pending leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    form = LeaveRequestForm(obj=leave_request)
    
    if form.validate_on_submit():
        leave_request.start_date = form.start_date.data
        leave_request.end_date = form.end_date.data
        leave_request.reason = form.reason.data
        
        db.session.commit()
        
        flash('Your leave request has been updated successfully!', 'success')
        return redirect(url_for('leave.index'))
    
    return render_template('leave/create.html',
                          title='Edit Leave Request',
                          form=form,
                          is_edit=True,
                          leave_request=leave_request)

@leave_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    """Delete a leave request (only if it's still pending and belongs to current user or if current user is admin)"""
    leave_request = LeaveRequest.query.get_or_404(id)
    
    # Check if user can delete this request
    if current_user.role == 'admin':
        # Admins can delete any pending leave request
        if leave_request.status != 'pending':
            flash('Admins can only delete pending leave requests.', 'danger')
            return redirect(url_for('leave.index'))
    elif leave_request.user_id != current_user.id:
        flash('You can only delete your own leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    if leave_request.status != 'pending':
        flash('You can only delete pending leave requests.', 'danger')
        return redirect(url_for('leave.index'))

    db.session.delete(leave_request)
    db.session.commit()
    flash('Leave request deleted successfully!', 'success')
    return redirect(url_for('leave.index'))


@leave_bp.route('/admin-create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create():
    """Allow admin to create leave requests on behalf of employees"""
    form = AdminLeaveRequestForm()
    
    # Populate employee dropdown with active employees
    if current_user.managed_department:
        # If admin is assigned to specific departments, show only employees from those departments
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        employees = User.query.filter(
            User.status == 'active',
            User.department_id.in_(admin_dept_ids)
        ).order_by(User.first_name).all()
    else:
        # If admin is not assigned to specific departments, show all active employees
        employees = User.query.filter_by(status='active').order_by(User.first_name).all()
    
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
            return redirect(url_for('leave.admin_create'))
        
        # Create the leave request for the employee
        leave_request = LeaveRequest(
            user_id=employee.id,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            reason=form.reason.data,
            status='pending'
        )
        
        # If the employee is a manager, automatically set manager_approved to True
        if employee.role == 'manager':
            leave_request.manager_approved = True
        
        db.session.add(leave_request)
        db.session.commit()
        
        # Notify the employee
        create_notification(
            user_id=employee.id,
            message=f"An admin has created a leave request on your behalf from {form.start_date.data} to {form.end_date.data}",
            notification_type='new_request',
            reference_id=leave_request.id,
            reference_type='leave'
        )
        
        # If employee is not a manager, notify their direct manager
        if employee.role != 'manager':
            managers = get_user_managers(employee)
            if managers['direct_manager']:
                create_notification(
                    user_id=managers['direct_manager'].id,
                    message=f"New leave request for {employee.get_full_name()} (created by admin) from {form.start_date.data} to {form.end_date.data}",
                    notification_type='new_request',
                    reference_id=leave_request.id,
                    reference_type='leave'
                )
        
        flash(f'Leave request for {employee.get_full_name()} has been submitted successfully!', 'success')
        return redirect(url_for('leave.index'))
    
    return render_template('leave/admin_create.html', 
                          title='Create Leave Request for Employee', 
                          form=form)
