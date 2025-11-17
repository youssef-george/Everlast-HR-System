import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date
from forms import LeaveRequestForm, ApprovalForm, AdminLeaveRequestForm, UpdateLeaveRequestForm
from models import db, LeaveRequest, User, LeaveType, LeaveBalance, PaidHoliday
from sqlalchemy import or_, and_
from sqlalchemy.exc import OperationalError
from helpers import role_required, get_user_managers, get_employees_for_manager, send_admin_email_notification
import logging
import time

leave_bp = Blueprint('leave', __name__, url_prefix='/leave')

def execute_with_retry(operation, max_retries=3, delay=0.1):
    """
    Execute a database operation with retry logic for handling database locks
    """
    for attempt in range(max_retries):
        try:
            return operation()
        except OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                logging.warning(f"Database locked on attempt {attempt + 1}, retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue
            else:
                raise
        except Exception as e:
            raise

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
                leave_requests = LeaveRequest.query.join(
                    User, LeaveRequest.user_id == User.id
                ).filter(
                    User.department_id.in_(managed_dept_ids),
                    LeaveRequest.user_id != current_user.id  # Exclude manager's own requests
                ).order_by(LeaveRequest.created_at.desc()).all()
    
    elif user_role == 'product_owner':
        # Product Owners see all leave requests by default
        if view_type == 'my':
            page_title = 'My Leave Requests'
            leave_requests = LeaveRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(LeaveRequest.created_at.desc()).all()
        else:
            page_title = 'All Leave Requests'
            # Product Owners see all requests regardless of department assignments
            leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    
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
                leave_requests = LeaveRequest.query.join(
                    User, LeaveRequest.user_id == User.id
                ).filter(
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
    
    
    elif user_role == 'director':
        # Directors see all leave requests
        page_title = 'All Company Leave Requests'
        leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
        
        # Get leave request statistics for director overview
        all_leave_requests = leave_requests
        pending_leave_requests = [req for req in leave_requests if req.status == 'pending']
        approved_leave_requests = [req for req in leave_requests if req.status == 'approved']
        rejected_leave_requests = [req for req in leave_requests if req.status == 'rejected']
    
    # Add pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    leave_requests_paginated = leave_requests[(page-1)*per_page:page*per_page]
    total_pages = (len(leave_requests) + per_page - 1) // per_page
    
    # Get departments for filter dropdown
    from models import Department
    departments = Department.query.all()
    
    # Prepare template variables
    template_vars = {
        'title': page_title,
        'leave_requests': leave_requests_paginated,
        'view_type': view_type,
        'total_pages': total_pages,
        'current_page': page,
        'total_records': len(leave_requests),
        'departments': departments
    }
    
    # Add director-specific overview data
    if user_role == 'director':
        template_vars.update({
            'all_leave_requests': all_leave_requests,
            'pending_leave_requests': pending_leave_requests,
            'approved_leave_requests': approved_leave_requests,
            'rejected_leave_requests': rejected_leave_requests,
            'show_director_overview': True
        })
    
    return render_template('leave/index.html', **template_vars)

@leave_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new leave request"""
    form = LeaveRequestForm()
    
    # Set leave type choices (PostgreSQL boolean comparison)
    leave_types = LeaveType.query.filter(LeaveType.is_active == True).all()
    form.leave_type_id.choices = [(lt.id, lt.name) for lt in leave_types] if leave_types else []

    # Set delegate employee choices
    employees = User.query.filter_by(status='active').order_by(User.first_name).all()
    delegate_choices = [(0, 'Select Delegate Employee')] + [(e.id, e.get_full_name()) for e in employees] if employees else [(0, 'Select Delegate Employee')]
    form.delegate_employee_id.choices = delegate_choices
    
    if form.validate_on_submit():
        # Check for paid holidays overlapping with the requested dates
        overlapping_holidays = PaidHoliday.query.filter(
            or_(
                # Single day holiday falls within the leave period
                and_(PaidHoliday.holiday_type == 'day',
                     PaidHoliday.start_date >= form.start_date.data,
                     PaidHoliday.start_date <= form.end_date.data),
                # Range holiday overlaps with the leave period
                and_(PaidHoliday.holiday_type == 'range',
                     PaidHoliday.start_date <= form.end_date.data,
                     PaidHoliday.end_date >= form.start_date.data)
            )
        ).all()
        
        if overlapping_holidays:
            # Check if there's a "Paid Leave" leave type
            paid_leave_type = LeaveType.query.filter_by(name='Paid Leave', is_active=True).first()
            if paid_leave_type and form.leave_type_id.data != paid_leave_type.id:
                # Suggest switching to paid leave
                holiday_descriptions = [h.description for h in overlapping_holidays]
                flash(f'Your leave request overlaps with paid holidays: {", ".join(holiday_descriptions)}. Consider selecting "Paid Leave" instead.', 'info')
                return render_template('leave/create.html', form=form, title='Create Leave Request')
            else:
                # If already paid leave or no paid leave type exists, just warn
                holiday_descriptions = [h.description for h in overlapping_holidays]
                flash(f'Your leave request overlaps with paid holidays: {", ".join(holiday_descriptions)}. Please adjust your dates.', 'warning')
                return render_template('leave/create.html', form=form, title='Create Leave Request')
        
        # Check if the selected leave type requires balance
        selected_leave_type = LeaveType.query.get(form.leave_type_id.data)
        if selected_leave_type and selected_leave_type.requires_balance:
            # Calculate days requested
            days_requested = (form.end_date.data - form.start_date.data).days + 1
            
            # Check leave balance
            leave_balance = LeaveBalance.query.filter_by(
                user_id=current_user.id,
                leave_type_id=form.leave_type_id.data,
                year=datetime.utcnow().year
            ).first()
            
            if not leave_balance or leave_balance.remaining_days < days_requested:
                flash(f'Insufficient leave balance. You have {leave_balance.remaining_days if leave_balance else 0} days remaining.', 'danger')
                return render_template('leave/create.html', form=form, title='Create Leave Request')
        
        leave_request = LeaveRequest(
            user_id=current_user.id,
            leave_type_id=form.leave_type_id.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            reason=form.reason.data,
            status='pending'
        )
        
        # If the current user is a manager, automatically set manager_status to approved
        if current_user.role == 'manager':
            leave_request.manager_status = 'approved'
        
        db.session.add(leave_request)
        db.session.commit()
        
        # Track if email was sent successfully
        email_sent = False
        
        # Send confirmation email to employee first
        try:
            from helpers import send_email_to_employee
            from flask import url_for
            
            leave_type_obj = LeaveType.query.get(form.leave_type_id.data)
            leave_type_name = leave_type_obj.name if leave_type_obj else "Leave"
            duration = (form.end_date.data - form.start_date.data).days + 1
            start_date_str = form.start_date.data.strftime('%B %d, %Y')
            end_date_str = form.end_date.data.strftime('%B %d, %Y')
            
            # Get submission timestamp
            submission_datetime = datetime.utcnow()
            submission_date_str = submission_datetime.strftime('%B %d, %Y')
            submission_time_str = submission_datetime.strftime('%I:%M %p')
            
            # Send employee confirmation email
            employee_request_data = {
                'request_type': 'Leave Request',
                'start_date': start_date_str,
                'end_date': end_date_str,
                'duration': f"{duration} day(s)",
                'reason': form.reason.data,
                'request_id': str(leave_request.id),
                'submission_date': submission_date_str,
                'submission_time': submission_time_str,
                'status': 'Pending Manager Review'
            }
            # Log email attempt details
            logging.info(f"=== LEAVE REQUEST EMAIL NOTIFICATION ===")
            logging.info(f"Employee: {current_user.id} - {current_user.get_full_name()}")
            logging.info(f"Email: {current_user.email}")
            logging.info(f"Request ID: {leave_request.id}")
            logging.info(f"Attempting to send submission confirmation email...")
            
            email_sent = send_email_to_employee(current_user, 'leave_employee_submission_confirmation', employee_request_data)
            
            if email_sent:
                logging.info(f"✅ SUCCESS: Employee confirmation email sent successfully to {current_user.email}")
            else:
                logging.error(f"❌ FAILED: Employee confirmation email NOT sent to {current_user.email}")
                logging.error(f"   Please check the logs above for detailed error information.")
                # Don't fail the request if email fails, but log it
        except Exception as e:
            logging.error(f"❌ Exception while sending employee confirmation email: {str(e)}", exc_info=True)
            # Don't fail the request if email fails
        
        # Send email notification to manager (or admin if no manager)
        try:
            from helpers import send_email_to_manager
            from flask import url_for
            
            leave_type_obj = LeaveType.query.get(form.leave_type_id.data)
            leave_type_name = leave_type_obj.name if leave_type_obj else "Leave"
            duration = (form.end_date.data - form.start_date.data).days + 1
            start_date_str = form.start_date.data.strftime('%B %d, %Y')
            end_date_str = form.end_date.data.strftime('%B %d, %Y')
            
            # Only send to manager if employee is not a manager (managers skip manager approval)
            if current_user.role != 'manager':
                approval_link = url_for('leave.view', id=leave_request.id, _external=True)
                request_data = {
                    'request_type': 'Leave Request',
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'duration': f"{duration} day(s)",
                    'reason': form.reason.data,
                    'request_id': str(leave_request.id),
                    'approval_link': approval_link
                }
                send_email_to_manager(current_user, 'leave_manager_notification', request_data)
            else:
                # If manager submits, send directly to admin
                from helpers import send_email_to_admin
                request_data = {
                    'request_type': 'Leave Request',
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'duration': f"{duration} day(s)",
                    'reason': form.reason.data,
                    'request_id': str(leave_request.id),
                    'approval_link': url_for('leave.view', id=leave_request.id, _external=True)
                }
                send_email_to_admin(current_user, 'leave_admin_notification', request_data)
        except Exception as e:
            logging.error(f"Failed to send email notification to manager/admin: {str(e)}", exc_info=True)
        
        # Show appropriate success message
        if email_sent:
            flash('Your leave request has been submitted and a confirmation email has been sent!', 'success')
        else:
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
    
    # Check if requester is a manager (special case)
    requester_is_manager = requester.role == 'manager'
    
    if user_role == 'manager':
        # Manager can approve if they are the department manager and request is pending manager approval
        # Note: If requester is a manager, their manager_status is already approved, so they skip this step
        if (requester.department and requester.department.manager_id == current_user.id and 
            leave_request.manager_status == 'pending'):
            can_approve = True
            approval_form = ApprovalForm()
    
    elif user_role in ['admin', 'product_owner']:
        # Admin/Product Owner can approve if:
        # 1. Request has manager approval and is pending admin approval (normal flow)
        # 2. OR if requester is manager, admin/product_owner can approve directly (manager requests skip manager approval)
        if ((leave_request.manager_status == 'approved' and leave_request.admin_status == 'pending') or
            (requester_is_manager and leave_request.admin_status == 'pending')):
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
            
            # Send email notification
            try:
                from helpers import send_email_to_admin, send_email_to_employee
                from flask import url_for
                
                leave_type_obj = LeaveType.query.get(leave_request.leave_type_id)
                leave_type_name = leave_type_obj.name if leave_type_obj else "Leave"
                duration = (leave_request.end_date - leave_request.start_date).days + 1
                
                if approval_status == 'approved':
                    # Manager approved - notify admin
                    request_data = {
                        'request_type': 'Leave Request',
                        'start_date': leave_request.start_date.strftime('%B %d, %Y'),
                        'end_date': leave_request.end_date.strftime('%B %d, %Y'),
                        'duration': f"{duration} day(s)",
                        'reason': leave_request.reason,
                        'comment': comment or 'Approved by manager',
                        'manager_name': current_user.get_full_name(),
                        'request_id': str(leave_request.id),
                        'approval_link': url_for('leave.view', id=leave_request.id, _external=True)
                    }
                    send_email_to_admin(requester, 'leave_admin_notification', request_data)
                else:
                    # Manager rejected - notify employee
                    request_data = {
                        'request_type': 'Leave Request',
                        'start_date': leave_request.start_date.strftime('%B %d, %Y'),
                        'end_date': leave_request.end_date.strftime('%B %d, %Y'),
                        'duration': f"{duration} day(s)",
                        'reason': leave_request.reason,
                        'comment': comment or 'Rejected by manager',
                        'status': 'Rejected',
                        'manager_name': current_user.get_full_name(),
                        'request_id': str(leave_request.id)
                    }
                    send_email_to_employee(requester, 'leave_employee_rejection', request_data)
            except Exception as e:
                logging.error(f"Failed to send email notification: {str(e)}")
        
        elif user_role in ['admin', 'product_owner']:
            leave_request.admin_status = approval_status
            leave_request.admin_comment = comment
            leave_request.admin_updated_at = datetime.utcnow()
            
            # Send email notification
            try:
                from helpers import send_email_to_employee
                
                leave_type_obj = LeaveType.query.get(leave_request.leave_type_id)
                leave_type_name = leave_type_obj.name if leave_type_obj else "Leave"
                duration = (leave_request.end_date - leave_request.start_date).days + 1
                
                if approval_status == 'approved':
                    # Admin approved - notify employee with confirmation
                    request_data = {
                        'request_type': 'Leave Request',
                        'start_date': leave_request.start_date.strftime('%B %d, %Y'),
                        'end_date': leave_request.end_date.strftime('%B %d, %Y'),
                        'duration': f"{duration} day(s)",
                        'reason': leave_request.reason,
                        'comment': comment or 'Approved',
                        'status': 'Approved',
                        'admin_name': current_user.get_full_name(),
                        'manager_name': requester.department.manager.get_full_name() if requester.department and requester.department.manager else 'Manager',
                        'request_id': str(leave_request.id)
                    }
                    send_email_to_employee(requester, 'leave_employee_confirmation', request_data)
                else:
                    # Admin rejected - notify employee
                    request_data = {
                        'request_type': 'Leave Request',
                        'start_date': leave_request.start_date.strftime('%B %d, %Y'),
                        'end_date': leave_request.end_date.strftime('%B %d, %Y'),
                        'duration': f"{duration} day(s)",
                        'reason': leave_request.reason,
                        'comment': comment or 'Rejected',
                        'status': 'Rejected',
                        'admin_name': current_user.get_full_name(),
                        'request_id': str(leave_request.id)
                    }
                    send_email_to_employee(requester, 'leave_employee_rejection', request_data)
            except Exception as e:
                logging.error(f"Failed to send email notification: {str(e)}")
        
        # Update overall status
        leave_request.update_overall_status()
        
        # Update daily attendance records if approved
        if approval_status == 'approved' and leave_request.status == 'approved':
            update_daily_attendance_for_leave(leave_request)
        elif approval_status == 'rejected' and leave_request.status == 'rejected':
            # If rejecting an approved leave request, refund the balance
            if leave_request.manager_status == 'approved' or leave_request.admin_status == 'approved':
                refund_leave_balance_for_leave(leave_request)
        
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
    """Edit a leave request. Product Owner can edit any request regardless of status. Admins/Directors can edit any request. Employees can only edit their own pending requests."""
    leave_request = LeaveRequest.query.get_or_404(id)
    
    # Check if user can edit this request
    if leave_request.user_id != current_user.id and current_user.role not in ['admin', 'product_owner', 'director']:
        flash('You can only edit your own leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    # Product Owner can edit any request regardless of status
    if leave_request.status != 'pending' and current_user.role not in ['admin', 'product_owner', 'director']:
        flash('You can only edit pending leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    form = LeaveRequestForm(obj=leave_request)

    # Set leave type choices (PostgreSQL boolean comparison)
    leave_types = LeaveType.query.filter(LeaveType.is_active == True).all()
    form.leave_type_id.choices = [(lt.id, lt.name) for lt in leave_types] if leave_types else []

    # Set delegate employee choices
    employees = User.query.filter_by(status='active').order_by(User.first_name).all()
    delegate_choices = [(0, 'Select Delegate Employee')] + [(e.id, e.get_full_name()) for e in employees] if employees else [(0, 'Select Delegate Employee')]
    form.delegate_employee_id.choices = delegate_choices

    if form.validate_on_submit():
        leave_request.start_date = form.start_date.data
        leave_request.end_date = form.end_date.data
        leave_request.reason = form.reason.data
        leave_request.delegate_employee_id = form.delegate_employee_id.data if form.delegate_employee_id.data != 0 else None
        
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
    """Delete a leave request. Product Owner can delete any request regardless of status. Admins can delete pending requests. Employees can only delete their own pending requests."""
    leave_request = LeaveRequest.query.get_or_404(id)
    
    # Check if user can delete this request
    if current_user.role == 'product_owner':
        # Product Owner can delete any leave request regardless of status
        pass  # No restrictions for Product Owner
    elif current_user.role == 'admin':
        # Admins can delete any pending leave request
        if leave_request.status != 'pending':
            flash('Admins can only delete pending leave requests.', 'danger')
            return redirect(url_for('leave.index'))
    elif leave_request.user_id != current_user.id:
        flash('You can only delete your own leave requests.', 'danger')
        return redirect(url_for('leave.index'))
    
    # Regular employees can only delete their own pending requests
    if leave_request.status != 'pending' and current_user.role not in ['product_owner']:
        flash('You can only delete pending leave requests.', 'danger')
        return redirect(url_for('leave.index'))

    try:
        def delete_operation():
            # Clean up attendance records and refund balance if this was an approved leave request
            if leave_request.status == 'approved':
                from models import DailyAttendance
                from datetime import timedelta
                
                # Refund leave balance first
                refund_leave_balance_for_leave(leave_request)
                
                # Update attendance records for the leave period
                current_date = leave_request.start_date
                while current_date <= leave_request.end_date:
                    daily_record = DailyAttendance.query.filter_by(
                        user_id=leave_request.user_id,
                        date=current_date
                    ).first()
                    
                    if daily_record and daily_record.status == 'leave':
                        # Reset to absent if no other attendance data exists
                        if not daily_record.first_check_in and not daily_record.last_check_out:
                            daily_record.status = 'absent'
                            daily_record.status_reason = None
                        else:
                            # If there's actual attendance data, reprocess the day
                            from routes.attendance import process_daily_attendance
                            process_daily_attendance(leave_request.user_id, current_date)
                    
                    current_date += timedelta(days=1)

            db.session.delete(leave_request)
            db.session.commit()
            return True

        # Execute with retry logic
        execute_with_retry(delete_operation)
        flash('Leave request deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting leave request: {str(e)}', 'danger')
    
    return redirect(url_for('leave.index'))


@leave_bp.route('/admin-create', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner', 'manager'])
def admin_create():
    """Allow admin to create leave requests on behalf of employees"""
    form = AdminLeaveRequestForm()
    
    # Initialize choices to empty lists immediately to prevent None errors
    form.employee_id.choices = []
    form.leave_type_id.choices = []
    form.delegate_employee_id.choices = []
    
    # Populate employee dropdown with active employees (excluding test users)
    current_app.logger.debug(f"Current user role: {current_user.role}")
    current_app.logger.debug(f"Form data received: {form.data}")
    if current_user.role == 'manager':
        try:
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

            current_app.logger.debug(f"Department employees: {[e.get_full_name() for e in department_employees.all()]}")

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
            current_app.logger.debug(f"Reporting employees: {[e.get_full_name() for e in reporting_employees.all()]}")
            
            # Combine and get unique employees
            employees = department_employees.union(reporting_employees).order_by(User.first_name).all()
        except Exception as e:
            current_app.logger.error(f"Error fetching employees for manager: {e}")
            employees = []
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
    if employees:
        for employee in employees:
            try:
                # Safely get department name - handle both department_name and name attributes
                if employee.department:
                    dept_name = getattr(employee.department, 'department_name', None) or getattr(employee.department, 'name', 'No Department')
                else:
                    dept_name = "No Department"
                display_text = f"{employee.get_full_name()} ({dept_name})"
                employee_choices.append((employee.id, display_text))
            except Exception as e:
                # Skip employees with invalid department relationships
                current_app.logger.warning(f"Error processing employee {employee.id} for choices: {e}")
                # Add employee without department name if possible
                try:
                    display_text = f"{employee.get_full_name()} (No Department)"
                    employee_choices.append((employee.id, display_text))
                except:
                    continue
    
    # Populate leave type dropdown with all active leave types for admin/manager
    # Use filter with boolean comparison for PostgreSQL compatibility
    leave_types = LeaveType.query.filter(LeaveType.is_active == True).all()
    leave_type_choices = [(lt.id, lt.name) for lt in leave_types] if leave_types else []
    
    # Ensure choices are never None - set to empty list if needed
    if not employee_choices:
        employee_choices = []
    if not leave_type_choices:
        leave_type_choices = []
    
    # Set choices for all fields - always set even if empty
    form.employee_id.choices = employee_choices if employee_choices else []
    form.leave_type_id.choices = leave_type_choices if leave_type_choices else []
    
    # Also set delegate employee choices
    delegate_employees = User.query.filter_by(status='active').order_by(User.first_name).all()
    delegate_choices = [(0, 'Select Delegate Employee')] + [(e.id, e.get_full_name()) for e in delegate_employees] if delegate_employees else [(0, 'Select Delegate Employee')]
    form.delegate_employee_id.choices = delegate_choices
    
    if form.validate_on_submit():
        # Get the selected employee
        employee = User.query.get(form.employee_id.data)
        
        if not employee:
            flash('Selected employee does not exist.', 'danger')
            return redirect(url_for('leave.admin_create'))
        
        # Validate that a valid leave type is selected
        selected_leave_type = LeaveType.query.get(form.leave_type_id.data)
        if not selected_leave_type:
            flash('Please select a valid leave type.', 'danger')
            return redirect(url_for('leave.admin_create'))
        
        # Validate if the manager is authorized to submit for this employee
        if current_user.role == 'manager':
            # Check if the selected employee is in the manager's department or reports to them
            is_in_department = (employee.department_id == current_user.department_id)
            is_direct_report = (employee.manager_id == current_user.id)

            if not (is_in_department or is_direct_report):
                flash('You can only submit requests for your team members.', 'danger')
                return redirect(url_for('leave.admin_create'))
        
        # Create the leave request for the employee
        leave_request = LeaveRequest(
            user_id=employee.id,
            leave_type_id=form.leave_type_id.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            reason=form.reason.data,
            status='approved'  # Auto-approve when created by admin
        )
        
        # Set all approval statuses to approved when created by admin
        leave_request.manager_status = 'approved'
        leave_request.admin_status = 'approved'
        
        db.session.add(leave_request)
        db.session.commit()
        
        # Update daily attendance records and deduct leave balance since it's auto-approved
        update_daily_attendance_for_leave(leave_request)
        
        # Employee notification removed - will be replaced with SMTP email notifications
        
        # Manager notification removed - will be replaced with SMTP email notifications
        
        flash(f'Leave request for {employee.get_full_name()} has been created and approved successfully!', 'success')
        return redirect(url_for('leave.index'))
    
    return render_template('leave/admin_create.html', 
                          title='Create Leave Request for Employee', 
                          form=form)

@leave_bp.route('/admin/edit/<int:leave_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def edit_leave(leave_id):
    """Edit a leave request (admin only) with last updated tracking"""
    leave_request = LeaveRequest.query.get_or_404(leave_id)
    
    # Create form and populate with existing data
    form = UpdateLeaveRequestForm(obj=leave_request)
    
    # Populate employee choices
    employees = User.query.filter_by(status='active').all()
    employee_choices = []
    if employees:
        for employee in employees:
            try:
                # Safely get department name - handle both department_name and name attributes
                if employee.department:
                    dept_name = getattr(employee.department, 'department_name', None) or getattr(employee.department, 'name', 'No Department')
                else:
                    dept_name = "No Department"
                display_text = f"{employee.get_full_name()} ({dept_name})"
                employee_choices.append((employee.id, display_text))
            except Exception as e:
                # Skip employees with invalid department relationships
                current_app.logger.warning(f"Error processing employee {employee.id} for choices: {e}")
                # Add employee without department name if possible
                try:
                    display_text = f"{employee.get_full_name()} (No Department)"
                    employee_choices.append((employee.id, display_text))
                except:
                    continue
    
    # Populate leave type choices (PostgreSQL boolean comparison)
    leave_types = LeaveType.query.filter(LeaveType.is_active == True).all()
    leave_type_choices = [(lt.id, lt.name) for lt in leave_types] if leave_types else []
    
    # Ensure choices are never None
    if not employee_choices:
        employee_choices = []
    if not leave_type_choices:
        leave_type_choices = []
    
    # Set choices for all fields - always set even if empty
    form.employee_id.choices = employee_choices
    form.leave_type_id.choices = leave_type_choices
    
    # Also set delegate employee choices
    delegate_employees = User.query.filter_by(status='active').order_by(User.first_name).all()
    delegate_choices = [(0, 'Select Delegate Employee')] + [(e.id, e.get_full_name()) for e in delegate_employees] if delegate_employees else [(0, 'Select Delegate Employee')]
    form.delegate_employee_id.choices = delegate_choices
    
    if form.validate_on_submit():
        try:
            # Update leave request data
            leave_request.user_id = form.employee_id.data
            leave_request.leave_type_id = form.leave_type_id.data
            leave_request.start_date = form.start_date.data
            leave_request.end_date = form.end_date.data
            leave_request.reason = form.reason.data
            leave_request.status = form.status.data
            
            # Add admin notes if provided
            if form.admin_notes.data:
                leave_request.admin_comment = form.admin_notes.data
            
            # Update last updated timestamp
            leave_request.updated_at = datetime.utcnow()
            leave_request.last_updated_by = current_user.id
            
            # If status is being changed, update the appropriate status fields
            if form.status.data == 'approved':
                leave_request.manager_status = 'approved'
                leave_request.admin_status = 'approved'
                leave_request.manager_updated_at = datetime.utcnow()
                leave_request.admin_updated_at = datetime.utcnow()
            elif form.status.data == 'rejected':
                leave_request.manager_status = 'rejected'
                leave_request.admin_status = 'rejected'
                leave_request.manager_updated_at = datetime.utcnow()
                leave_request.admin_updated_at = datetime.utcnow()
            else:  # pending
                leave_request.manager_status = 'pending'
                leave_request.admin_status = 'pending'
            
            db.session.commit()
            
            # Update daily attendance records and deduct leave balance if approved
            if form.status.data == 'approved':
                update_daily_attendance_for_leave(leave_request)
            
            flash(f'Leave request has been updated successfully!', 'success')
            return redirect(url_for('leave.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating leave request: {str(e)}', 'danger')
    
    return render_template('leave/edit.html', 
                          title='Edit Leave Request', 
                          form=form, 
                          leave_request=leave_request)

@leave_bp.route('/admin/delete/<int:leave_id>', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def delete_leave(leave_id):
    """Delete a leave request (admin only)"""
    leave_request = LeaveRequest.query.get_or_404(leave_id)
    employee_name = leave_request.user.get_full_name()
    
    try:
        def admin_delete_operation():
            # Clean up attendance records and refund balance if this was an approved leave request
            if leave_request.status == 'approved':
                from models import DailyAttendance
                from datetime import timedelta
                
                # Refund leave balance first
                refund_leave_balance_for_leave(leave_request)
                
                # Update attendance records for the leave period
                current_date = leave_request.start_date
                while current_date <= leave_request.end_date:
                    daily_record = DailyAttendance.query.filter_by(
                        user_id=leave_request.user_id,
                        date=current_date
                    ).first()
                    
                    if daily_record and daily_record.status == 'leave':
                        # Reset to absent if no other attendance data exists
                        if not daily_record.first_check_in and not daily_record.last_check_out:
                            daily_record.status = 'absent'
                            daily_record.status_reason = None
                        else:
                            # If there's actual attendance data, reprocess the day
                            from routes.attendance import process_daily_attendance
                            process_daily_attendance(leave_request.user_id, current_date)
                    
                    current_date += timedelta(days=1)
            
            db.session.delete(leave_request)
            db.session.commit()
            return True

        # Execute with retry logic
        execute_with_retry(admin_delete_operation)
        flash(f'Leave request for {employee_name} has been deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting leave request: {str(e)}', 'danger')
    
    return redirect(url_for('leave.index'))

def update_daily_attendance_for_leave(leave_request):
    """Update daily attendance records for an approved leave request"""
    from models import DailyAttendance, LeaveType, PaidHoliday
    from datetime import timedelta
    
    try:
        # Get leave type information
        leave_type = LeaveType.query.get(leave_request.leave_type_id)
        if not leave_type:
            logging.error(f"Leave type not found for leave request {leave_request.id}")
            return
        
        # Generate date range for the leave
        current_date = leave_request.start_date
        end_date = leave_request.end_date
        
        while current_date <= end_date:
            # Check if attendance record already exists
            existing_attendance = DailyAttendance.query.filter_by(
                user_id=leave_request.user_id,
                date=current_date
            ).first()
            
            # Check if this date is a paid holiday
            paid_holiday = PaidHoliday.query.filter(
                PaidHoliday.start_date <= current_date,
                PaidHoliday.end_date >= current_date
            ).first()
            
            if existing_attendance:
                # Update existing record
                if paid_holiday and existing_attendance.is_paid_holiday:
                    # Handle overlap: Paid Leave / Present
                    existing_attendance.status = 'leave'
                    existing_attendance.leave_request_id = leave_request.id
                    existing_attendance.leave_type_id = leave_request.leave_type_id
                    existing_attendance.leave_type_name = f"{leave_type.name} / Present"
                    # Keep paid holiday info for reference
                    existing_attendance.holiday_name = f"{paid_holiday.description} / {leave_type.name}"
                else:
                    # Regular leave update
                    existing_attendance.status = 'leave'
                    existing_attendance.leave_request_id = leave_request.id
                    existing_attendance.leave_type_id = leave_request.leave_type_id
                    existing_attendance.leave_type_name = leave_type.name
            else:
                # Create new record
                if paid_holiday:
                    # Paid holiday overlap
                    attendance = DailyAttendance(
                        user_id=leave_request.user_id,
                        date=current_date,
                        status='leave',
                        leave_request_id=leave_request.id,
                        leave_type_id=leave_request.leave_type_id,
                        leave_type_name=f"{leave_type.name} / Present",
                        is_paid_holiday=True,
                        paid_holiday_id=paid_holiday.id,
                        holiday_name=f"{paid_holiday.description} / {leave_type.name}"
                    )
                else:
                    # Regular leave
                    attendance = DailyAttendance(
                        user_id=leave_request.user_id,
                        date=current_date,
                        status='leave',
                        leave_request_id=leave_request.id,
                        leave_type_id=leave_request.leave_type_id,
                        leave_type_name=leave_type.name
                    )
                db.session.add(attendance)
            
            current_date += timedelta(days=1)
        
        # Update leave balance if the leave type requires balance
        if leave_type.requires_balance:
            update_leave_balance_for_leave(leave_request)
        
        logging.info(f"Updated daily attendance for leave request {leave_request.id}")
        
    except Exception as e:
        logging.error(f"Error updating daily attendance for leave: {str(e)}")
        raise

def update_leave_balance_for_leave(leave_request):
    """Update leave balance when a leave request is approved"""
    from models import LeaveBalance, LeaveType
    from datetime import datetime
    
    try:
        # Get the leave type to check if it requires balance deduction
        leave_type = LeaveType.query.get(leave_request.leave_type_id)
        if not leave_type:
            logging.warning(f"Leave type {leave_request.leave_type_id} not found")
            return
        
        # Only deduct from balance if the leave type requires it
        if not leave_type.requires_balance:
            logging.info(f"Leave type '{leave_type.name}' does not require balance deduction")
            return
        
        # Calculate number of days
        days_count = (leave_request.end_date - leave_request.start_date).days + 1
        
        # Get or create leave balance for this year
        current_year = datetime.now().year
        balance = LeaveBalance.query.filter_by(
            user_id=leave_request.user_id,
            leave_type_id=leave_request.leave_type_id,
            year=current_year
        ).first()
        
        if balance:
            # Update existing balance
            balance.used_days = (balance.used_days or 0) + days_count
            # Allow negative remaining days
            balance.remaining_days = balance.total_days - balance.used_days
            # Update manual remaining days if it was set
            if balance.manual_remaining_days is not None:
                balance.manual_remaining_days = balance.remaining_days
        else:
            # Create new balance for leave types that require balance
            balance = LeaveBalance(
                user_id=leave_request.user_id,
                leave_type_id=leave_request.leave_type_id,
                total_days=0,
                used_days=days_count,
                remaining_days=-days_count,  # Allow negative values
                year=current_year
            )
            db.session.add(balance)
        
        # Execute with retry logic
        execute_with_retry(lambda: db.session.commit())
        logging.info(f"Updated leave balance for user {leave_request.user_id}: {days_count} days used for {leave_type.name}")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating leave balance: {str(e)}")
        raise

def refund_leave_balance_for_leave(leave_request):
    """Refund leave balance when a leave request is deleted or rejected"""
    from models import LeaveBalance, LeaveType
    from datetime import datetime
    
    try:
        # Get the leave type to check if it requires balance deduction
        leave_type = LeaveType.query.get(leave_request.leave_type_id)
        if not leave_type:
            logging.warning(f"Leave type {leave_request.leave_type_id} not found")
            return
        
        # Only refund balance if the leave type requires it
        if not leave_type.requires_balance:
            logging.info(f"Leave type '{leave_type.name}' does not require balance refund")
            return
        
        # Calculate number of days to refund
        days_count = (leave_request.end_date - leave_request.start_date).days + 1
        
        # Get leave balance for this year
        current_year = datetime.now().year
        balance = LeaveBalance.query.filter_by(
            user_id=leave_request.user_id,
            leave_type_id=leave_request.leave_type_id,
            year=current_year
        ).first()
        
        if balance:
            # Refund the days
            balance.used_days = max(0, (balance.used_days or 0) - days_count)
            # Recalculate remaining days
            balance.remaining_days = balance.total_days - balance.used_days
            # Update manual remaining days if it was set
            if balance.manual_remaining_days is not None:
                balance.manual_remaining_days = balance.remaining_days
            
            # Execute with retry logic
            execute_with_retry(lambda: db.session.commit())
            logging.info(f"Refunded leave balance for user {leave_request.user_id}: {days_count} days refunded for {leave_type.name}")
        else:
            logging.warning(f"No leave balance found to refund for user {leave_request.user_id} and leave type {leave_type.name}")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error refunding leave balance: {str(e)}")
        raise

@leave_bp.route('/my-leave-balance')
@login_required
def my_leave_balance():
    """API endpoint to get current user's leave balance for sidebar widget"""
    try:
        if current_user.role != 'employee':
            return jsonify({'error': 'Access denied'}), 403
        
        # Get all leave balances for the current user
        leave_balances = LeaveBalance.query.filter_by(user_id=current_user.id).all()
        
        if not leave_balances:
            return jsonify({
                'status': 'success',
                'balances': [],
                'message': 'No leave balance data available'
            })
        
        # Format the data for the widget
        balances_data = []
        for balance in leave_balances:
            if balance.leave_type:
                balances_data.append({
                    'leave_type': balance.leave_type.name,
                    'total_days': balance.total_days,
                    'remaining_days': balance.remaining_days,
                    'used_days': balance.total_days - balance.remaining_days
                })
        
        return jsonify({
            'status': 'success',
            'balances': balances_data
        })
        
    except Exception as e:
        logging.error(f"Error fetching leave balance for user {current_user.id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load leave balance'
        }), 500

@leave_bp.route('/my-balance')
@login_required
def my_balance():
    """Dedicated page showing employee's leave balance with detailed UI"""
    if current_user.role != 'employee':
        flash('Access denied. This page is only available for employees.', 'error')
        return redirect(url_for('dashboard.index'))
    
    # Get all leave balances for the current user
    leave_balances = LeaveBalance.query.filter_by(user_id=current_user.id).all()
    
    # Get recent leave requests for context
    recent_requests = LeaveRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
    
    # Calculate summary statistics
    total_leave_days = sum(balance.total_days for balance in leave_balances)
    total_remaining_days = sum(balance.remaining_days for balance in leave_balances)
    total_used_days = total_leave_days - total_remaining_days
    
    return render_template('leave/my_balance.html', 
                         title='My Leave Balance',
                         leave_balances=leave_balances,
                         recent_requests=recent_requests,
                         total_leave_days=total_leave_days,
                         total_remaining_days=total_remaining_days,
                         total_used_days=total_used_days)
