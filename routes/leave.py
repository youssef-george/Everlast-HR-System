from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date
from forms import LeaveRequestForm, ApprovalForm
from models import LeaveRequest, User
from app import db
from helpers import role_required, create_notification, get_user_managers, get_employees_for_manager

leave_bp = Blueprint('leave', __name__, url_prefix='/leave')

@leave_bp.route('/')
@login_required
def index():
    """List leave requests based on user role"""
    user_role = current_user.role
    leave_requests = []
    
    if user_role == 'employee':
        # Employees see only their own leave requests
        leave_requests = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'manager':
        # Managers see leave requests from their department employees
        employees = get_employees_for_manager(current_user.id)
        employee_ids = [emp.id for emp in employees]
        
        if employee_ids:
            leave_requests = LeaveRequest.query.filter(
                LeaveRequest.user_id.in_(employee_ids)
            ).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'admin':
        # Admins see all leave requests
        leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'director':
        # Directors see all leave requests
        leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    
    return render_template('leave/index.html', 
                           title='Leave Requests', 
                           leave_requests=leave_requests)

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
        # First, check if current user is the manager of the requester's department
        if requester.department and requester.department.manager_id == current_user.id:
            if leave_request.status == 'pending' and not leave_request.manager_approved:
                can_approve = True
                approval_form = ApprovalForm()
        # If not explicitly set as department manager, check if they're in the same dept with manager role
        elif requester.department_id and requester.department_id == current_user.department_id:
            if leave_request.status == 'pending' and not leave_request.manager_approved:
                can_approve = True
                approval_form = ApprovalForm()
    
    elif user_role == 'admin':
        # Get the department of the requester
        requester_department = requester.department
        
        # Admins can approve if status is pending, manager has approved, and request is from their department
        if leave_request.status == 'pending' and leave_request.manager_approved and not leave_request.admin_approved:
            # If the admin is specifically assigned to handle a department (through managed_department relationship)
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
                leave_request.manager_approved = True
                
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
                        message=f"Leave request from {requester.get_full_name()} ({requester.department.department_name if requester.department else 'No Department'}) approved by manager and needs your review",
                        notification_type='approval',
                        reference_id=leave_request.id,
                        reference_type='leave'
                    )
                
                flash('Leave request has been approved as manager.', 'success')
            
            elif user_role == 'admin':
                leave_request.admin_approved = True
                leave_request.status = 'approved'
                
                # Notify the employee
                create_notification(
                    user_id=requester.id,
                    message=f"Your leave request from {leave_request.start_date} to {leave_request.end_date} has been approved",
                    notification_type='approval',
                    reference_id=leave_request.id,
                    reference_type='leave'
                )
                
                flash('Leave request has been approved.', 'success')
        
        elif approval_form.status.data == 'rejected':
            leave_request.status = 'rejected'
            
            # Notify the employee
            create_notification(
                user_id=requester.id,
                message=f"Your leave request from {leave_request.start_date} to {leave_request.end_date} has been rejected",
                notification_type='rejection',
                reference_id=leave_request.id,
                reference_type='leave'
            )
            
            flash('Leave request has been rejected.', 'warning')
        
        # Add comment if provided
        if approval_form.comment.data:
            leave_request.comment = approval_form.comment.data
            
            # Notify the employee about the comment
            create_notification(
                user_id=requester.id,
                message=f"New comment on your leave request: {approval_form.comment.data[:50]}...",
                notification_type='comment',
                reference_id=leave_request.id,
                reference_type='leave'
            )
        
        db.session.commit()
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
                          is_edit=True)

@leave_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    """Delete a leave request (only if it's still pending and belongs to current user)"""
    leave_request = LeaveRequest.query.get_or_404(id)
    
    # Check if user can delete this request
    if leave_request.user_id != current_user.id:
        flash('You can only delete your own leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    if leave_request.status != 'pending':
        flash('You can only delete pending leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    db.session.delete(leave_request)
    db.session.commit()
    
    flash('Your leave request has been deleted successfully!', 'success')
    return redirect(url_for('leave.index'))
