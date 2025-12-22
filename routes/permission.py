from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date, time
from forms import PermissionRequestForm, ApprovalForm, AdminPermissionRequestForm
from models import db, PermissionRequest, User
from helpers import role_required, get_user_managers, get_employees_for_manager, send_admin_email_notification, log_activity
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
    
    elif user_role == 'product_owner':
        # Technical Support see all permission requests regardless of department assignments
        page_title = 'All Permission Requests'
        permission_requests = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).all()
    
    elif user_role == 'admin':
        if view_type == 'my':
            page_title = 'My Permission Requests'
            permission_requests = PermissionRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(PermissionRequest.created_at.desc()).all()
        elif view_type == 'all':
            page_title = 'All Permission Requests'
            # Show all requests if explicitly requested
            permission_requests = PermissionRequest.query.order_by(PermissionRequest.created_at.desc()).all()
        else:
            # Default: Show requests pending admin approval
            page_title = 'Permission Requests for Approval'
            # Get requests that need admin approval based on department assignments
            if current_user.managed_department:
                admin_dept_ids = [dept.id for dept in current_user.managed_department]
                permission_requests = PermissionRequest.query.join(
                    User, PermissionRequest.user_id == User.id
                ).filter(
                    PermissionRequest.manager_status == 'approved',
                    PermissionRequest.admin_status == 'pending',
                    User.department_id.in_(admin_dept_ids)
                ).order_by(PermissionRequest.created_at.desc()).all()
            else:
                # If not assigned to specific departments, show all pending admin approvals
                permission_requests = PermissionRequest.query.filter_by(
                    manager_status='approved',
                    admin_status='pending'
                ).order_by(PermissionRequest.created_at.desc()).all()
    
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
        
        # Allow all dates including past dates - no date restriction
        
        permission_request = PermissionRequest(
            user_id=current_user.id,
            start_time=start_datetime,
            end_time=end_datetime,
            reason=form.reason.data,
            status='pending'
        )
        
        # If the current user is a manager or director, automatically set manager_status to approved
        if current_user.role in ['manager', 'director']:
            permission_request.manager_status = 'approved'
        
        db.session.add(permission_request)
        db.session.commit()
        
        # Log permission request creation
        start_date_str = form.start_date.data.strftime('%Y-%m-%d')
        start_time_str = form.start_time.data.strftime('%H:%M')
        end_time_str = form.end_time.data.strftime('%H:%M')
        duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
        
        log_activity(
            user=current_user,
            action='create_permission_request',
            entity_type='permission_request',
            entity_id=permission_request.id,
            before_values=None,
            after_values={
                'start_date': start_date_str,
                'start_time': start_time_str,
                'end_time': end_time_str,
                'duration_hours': round(duration_hours, 2),
                'reason': form.reason.data[:100] if len(form.reason.data) > 100 else form.reason.data,
                'status': 'pending',
                'manager_status': 'approved' if current_user.role in ['manager', 'director'] else 'pending'
            },
            description=f'User {current_user.get_full_name()} created a permission request for {duration_hours:.1f} hour(s) on {start_date_str}'
        )
        
        # Send confirmation email to employee first
        try:
            from helpers import send_email_to_employee
            
            start_date_str = form.start_date.data.strftime('%B %d, %Y')
            start_time_str = form.start_time.data.strftime('%I:%M %p')
            end_time_str = form.end_time.data.strftime('%I:%M %p')
            duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
            
            # Get submission timestamp
            submission_datetime = datetime.utcnow()
            submission_date_str = submission_datetime.strftime('%B %d, %Y')
            submission_time_str = submission_datetime.strftime('%I:%M %p')
            
            # Send employee confirmation email
            employee_request_data = {
                'request_type': 'Permission Request',
                'start_date': start_date_str,
                'end_date': f"{start_time_str} - {end_time_str}",
                'duration': f"{duration_hours:.1f} hour(s)",
                'reason': form.reason.data,
                'request_id': str(permission_request.id),
                'submission_date': submission_date_str,
                'submission_time': submission_time_str,
                'status': 'Pending Manager Review'
            }
            email_sent = send_email_to_employee(current_user, 'permission_employee_submission_confirmation', employee_request_data)
            if email_sent:
                logging.info(f"Employee confirmation email sent successfully to {current_user.email}")
            else:
                logging.warning(f"Failed to send employee confirmation email to {current_user.email}")
        except Exception as e:
            logging.error(f"Exception while sending employee confirmation email: {str(e)}", exc_info=True)
        
        # Send email notification to manager (or admin if no manager)
        manager_email_sent = False
        try:
            from helpers import send_email_to_manager, send_email_to_admin
            
            start_date_str = form.start_date.data.strftime('%B %d, %Y')
            start_time_str = form.start_time.data.strftime('%I:%M %p')
            end_time_str = form.end_time.data.strftime('%I:%M %p')
            duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
            
            # Only send to manager if employee is not a manager or director (managers and directors skip manager approval)
            if current_user.role not in ['manager', 'director']:
                approval_link = url_for('permission.view', id=permission_request.id, _external=True)
                request_data = {
                    'request_type': 'Permission Request',
                    'start_date': start_date_str,
                    'end_date': f"{start_time_str} - {end_time_str}",
                    'duration': f"{duration_hours:.1f} hour(s)",
                    'reason': form.reason.data,
                    'request_id': str(permission_request.id),
                    'approval_link': approval_link
                }
                logging.info(f"=== SENDING EMAIL TO MANAGER ===")
                logging.info(f"Employee: {current_user.get_full_name()} ({current_user.email})")
                logging.info(f"Request ID: {permission_request.id}")
                manager_email_sent = send_email_to_manager(current_user, 'permission_manager_notification', request_data)
                if manager_email_sent:
                    logging.info(f"✅ Manager notification email sent successfully")
                else:
                    logging.error(f"❌ Manager notification email NOT sent - check logs above for details")
            else:
                # If manager or director submits, send directly to admin
                request_data = {
                    'request_type': 'Permission Request',
                    'start_date': start_date_str,
                    'end_date': f"{start_time_str} - {end_time_str}",
                    'duration': f"{duration_hours:.1f} hour(s)",
                    'reason': form.reason.data,
                    'request_id': str(permission_request.id),
                    'approval_link': url_for('permission.view', id=permission_request.id, _external=True)
                }
                logging.info(f"=== SENDING EMAIL TO ADMIN ===")
                logging.info(f"Employee: {current_user.get_full_name()} ({current_user.email})")
                logging.info(f"Request ID: {permission_request.id}")
                manager_email_sent = send_email_to_admin(current_user, 'permission_admin_notification', request_data)
                if manager_email_sent:
                    logging.info(f"✅ Admin notification email sent successfully")
                else:
                    logging.error(f"❌ Admin notification email NOT sent - check logs above for details")
        except Exception as e:
            logging.error(f"❌ Exception while sending email notification to manager/admin: {str(e)}", exc_info=True)
        
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
    
    # Check if requester is a manager or director (special case - managers/directors skip manager approval)
    requester_is_manager = requester.role == 'manager'
    requester_is_director = requester.role == 'director'
    
    if user_role == 'manager':
        # Manager can approve if they are the department manager and request is pending manager approval
        # Note: If requester is a manager or director, their manager_status is already approved, so they skip this step
        if (requester.department and requester.department.manager_id == current_user.id and 
            permission_request.manager_status == 'pending'):
            can_approve = True
            approval_form = ApprovalForm()
    
    elif user_role == 'director':
        # Directors cannot approve their own requests - only admin can approve director requests
        # Directors can view all requests but cannot approve any (including their own)
        # This ensures all director requests must be approved by admin only
        can_approve = False
        approval_form = None
    
    elif user_role in ['admin', 'product_owner']:
        # Admin/Technical Support can approve if:
        # 1. Request has manager approval and is pending admin approval (normal flow)
        # 2. OR if requester is manager or director, admin/product_owner can approve directly (manager/director requests skip manager approval)
        if ((permission_request.manager_status == 'approved' and permission_request.admin_status == 'pending') or
            ((requester_is_manager or requester_is_director) and permission_request.admin_status == 'pending')):
            can_approve = True
            approval_form = ApprovalForm()
    
    # Handle approval/rejection submission
    if approval_form and approval_form.validate_on_submit():
        try:
            approval_status = approval_form.status.data
            comment = approval_form.comment.data
            
            if user_role == 'manager':
                # Capture before status for logging
                before_status = {
                    'manager_status': permission_request.manager_status,
                    'admin_status': permission_request.admin_status,
                    'overall_status': permission_request.status
                }
                
                permission_request.manager_status = approval_status
                permission_request.manager_comment = comment
                permission_request.manager_updated_at = datetime.utcnow()
                
                # Send email notification
                try:
                    from helpers import send_email_to_admin, send_email_to_employee
                    
                    start_date_str = permission_request.start_time.strftime('%B %d, %Y')
                    start_time_str = permission_request.start_time.strftime('%I:%M %p')
                    end_time_str = permission_request.end_time.strftime('%I:%M %p')
                    duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
                    
                    if approval_status == 'approved':
                        # Manager approved - notify admin
                        request_data = {
                            'request_type': 'Permission Request',
                            'start_date': start_date_str,
                            'end_date': f"{start_time_str} - {end_time_str}",
                            'duration': f"{duration_hours:.1f} hour(s)",
                            'reason': permission_request.reason,
                            'comment': comment or 'Approved by manager',
                            'manager_name': current_user.get_full_name(),
                            'request_id': str(permission_request.id),
                            'approval_link': url_for('permission.view', id=permission_request.id, _external=True)
                        }
                        send_email_to_admin(requester, 'permission_admin_notification', request_data)
                    else:
                        # Manager rejected - notify employee
                        request_data = {
                            'request_type': 'Permission Request',
                            'start_date': start_date_str,
                            'end_date': f"{start_time_str} - {end_time_str}",
                            'duration': f"{duration_hours:.1f} hour(s)",
                            'reason': permission_request.reason,
                            'comment': comment or 'Rejected by manager',
                            'status': 'Rejected',
                            'manager_name': current_user.get_full_name(),
                            'request_id': str(permission_request.id)
                        }
                        send_email_to_employee(requester, 'permission_employee_rejection', request_data)
                except Exception as e:
                    logging.error(f"Failed to send email notification: {str(e)}")
                
                # Update overall status (if not already updated in admin approval section)
                try:
                    old_status = permission_request.status
                    permission_request.update_overall_status()
                    # Explicitly mark the status field as modified to ensure SQLAlchemy tracks the change
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(permission_request, 'status')
                    # Explicitly mark the object as modified to ensure SQLAlchemy tracks the change
                    db.session.add(permission_request)
                    logging.info(f"Manager approval: Updated permission request #{permission_request.id} status from '{old_status}' to '{permission_request.status}'")
                except Exception as status_error:
                    logging.error(f"Error updating overall status: {str(status_error)}", exc_info=True)
                    # Continue even if status update fails
                
                # Log permission request approval/rejection (after status update)
                start_date_str = permission_request.start_time.strftime('%Y-%m-%d')
                start_time_str = permission_request.start_time.strftime('%H:%M')
                end_time_str = permission_request.end_time.strftime('%H:%M')
                duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
                
                # Get the status after update (don't refresh before commit to avoid stale data)
                # The status should already be updated by update_overall_status()
                after_status = {
                    'manager_status': permission_request.manager_status,
                    'admin_status': permission_request.admin_status,
                    'overall_status': permission_request.status
                }
                
                approver_role = 'Manager'
                action_name = f'{user_role}_approve_permission_request' if approval_status == 'approved' else f'{user_role}_reject_permission_request'
                log_activity(
                    user=current_user,
                    action=action_name,
                    entity_type='permission_request',
                    entity_id=permission_request.id,
                    before_values=before_status,
                    after_values=after_status,
                    description=f'{approver_role} {current_user.get_full_name()} {approval_status} permission request #{permission_request.id} ({duration_hours:.1f} hour(s) on {start_date_str}) by {requester.get_full_name()}'
                )
                
                # Flush changes to database before commit to ensure status is saved
                db.session.flush()
                
                # Verify the status was updated correctly before commit
                if approval_status == 'approved':
                    # Ensure status is updated one more time before commit
                    permission_request.update_overall_status()
                    # Explicitly set and flag the status to ensure it's saved
                    final_status = permission_request.status
                    permission_request.status = final_status
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(permission_request, 'status')
                    db.session.add(permission_request)
                    logging.info(f"Before commit - Permission request #{permission_request.id} status: {final_status}, manager_status: {permission_request.manager_status}, admin_status: {permission_request.admin_status}")
                
                # Commit all changes including status update
                db.session.commit()
                
                # Verify after commit by re-querying from database
                db.session.expire(permission_request)
                verified_request = PermissionRequest.query.get(permission_request.id)
                logging.info(f"After commit (verified from DB) - Permission request #{permission_request.id} status: {verified_request.status}, manager_status: {verified_request.manager_status}, admin_status: {verified_request.admin_status}")
                
                flash(f'Permission request has been {approval_status}.', 'success')
                return redirect(url_for('permission.index'))
        
            elif user_role in ['admin', 'product_owner']:
                # Capture before status for logging
                before_status = {
                    'manager_status': permission_request.manager_status,
                    'admin_status': permission_request.admin_status,
                    'overall_status': permission_request.status
                }
                
                permission_request.admin_status = approval_status
                permission_request.admin_comment = comment
                permission_request.admin_updated_at = datetime.utcnow()
                
                # If requester is a manager and admin is approving, ensure manager_status is also approved
                # (Manager requests skip manager approval, so manager_status should already be approved,
                # but we ensure it's set correctly here)
                if approval_status == 'approved' and requester_is_manager and permission_request.manager_status != 'approved':
                    permission_request.manager_status = 'approved'
                    permission_request.manager_updated_at = datetime.utcnow()
                
                # Update overall status immediately after setting admin_status
                old_status = permission_request.status
                permission_request.update_overall_status()
                new_status = permission_request.status
                
                # Explicitly mark the status field as modified to ensure SQLAlchemy tracks the change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(permission_request, 'status')
                
                # Log the status update for debugging
                logging.info(f"Admin approval: Updated permission request #{permission_request.id} status from '{old_status}' to '{new_status}' (manager_status: {permission_request.manager_status}, admin_status: {permission_request.admin_status})")
                
                # Explicitly mark the object as modified to ensure SQLAlchemy tracks the change
                db.session.add(permission_request)
                
                # Log permission request approval/rejection
                start_date_str = permission_request.start_time.strftime('%Y-%m-%d')
                start_time_str = permission_request.start_time.strftime('%H:%M')
                end_time_str = permission_request.end_time.strftime('%H:%M')
                duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
                
                after_status = {
                    'manager_status': permission_request.manager_status,
                    'admin_status': permission_request.admin_status,
                    'overall_status': permission_request.status
                }
                
                log_activity(
                    user=current_user,
                    action='admin_approve_permission_request' if approval_status == 'approved' else 'admin_reject_permission_request',
                    entity_type='permission_request',
                    entity_id=permission_request.id,
                    before_values=before_status,
                    after_values=after_status,
                    description=f'Admin/Technical Support {current_user.get_full_name()} {approval_status} permission request #{permission_request.id} ({duration_hours:.1f} hour(s) on {start_date_str}) by {requester.get_full_name()}'
                )
                
                # Send email notification (after commit to ensure data is saved)
                try:
                    from helpers import send_email_to_employee
                    
                    start_date_str = permission_request.start_time.strftime('%B %d, %Y')
                    start_time_str = permission_request.start_time.strftime('%I:%M %p')
                    end_time_str = permission_request.end_time.strftime('%I:%M %p')
                    duration_hours = (permission_request.end_time - permission_request.start_time).total_seconds() / 3600
                    
                    if approval_status == 'approved':
                        # Admin approved - notify employee with confirmation
                        # Safely get manager name
                        manager_name = 'Manager'
                        try:
                            if requester.department and requester.department.manager:
                                manager_name = requester.department.manager.get_full_name()
                        except (AttributeError, Exception):
                            manager_name = 'Manager'
                        
                        request_data = {
                            'request_type': 'Permission Request',
                            'start_date': start_date_str,
                            'end_date': f"{start_time_str} - {end_time_str}",
                            'duration': f"{duration_hours:.1f} hour(s)",
                            'reason': permission_request.reason,
                            'comment': comment or 'Approved',
                            'status': 'Approved',
                            'admin_name': current_user.get_full_name(),
                            'manager_name': manager_name,
                            'request_id': str(permission_request.id)
                        }
                        send_email_to_employee(requester, 'permission_employee_confirmation', request_data)
                    else:
                        # Admin rejected - notify employee
                        request_data = {
                            'request_type': 'Permission Request',
                            'start_date': start_date_str,
                            'end_date': f"{start_time_str} - {end_time_str}",
                            'duration': f"{duration_hours:.1f} hour(s)",
                            'reason': permission_request.reason,
                            'comment': comment or 'Rejected',
                            'status': 'Rejected',
                            'admin_name': current_user.get_full_name(),
                            'request_id': str(permission_request.id)
                        }
                        send_email_to_employee(requester, 'permission_employee_rejection', request_data)
                except Exception as e:
                    logging.error(f"Failed to send email notification: {str(e)}")
                    # Don't fail the whole operation if email fails - status is already saved
                
                # Flush changes to database before commit to ensure status is saved
                db.session.flush()
                
                # Verify the status was updated correctly before commit
                if approval_status == 'approved':
                    # Ensure status is updated one more time before commit
                    permission_request.update_overall_status()
                    # Explicitly set and flag the status to ensure it's saved
                    final_status = permission_request.status
                    permission_request.status = final_status
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(permission_request, 'status')
                    db.session.add(permission_request)
                    logging.info(f"Before commit - Permission request #{permission_request.id} status: {final_status}, manager_status: {permission_request.manager_status}, admin_status: {permission_request.admin_status}")
                
                # Commit all changes including status update
                db.session.commit()
                
                # Verify after commit by re-querying from database
                db.session.expire(permission_request)
                verified_request = PermissionRequest.query.get(permission_request.id)
                logging.info(f"After commit (verified from DB) - Permission request #{permission_request.id} status: {verified_request.status}, manager_status: {verified_request.manager_status}, admin_status: {verified_request.admin_status}")
                
                flash(f'Permission request has been {approval_status}.', 'success')
                return redirect(url_for('permission.index'))
        
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing permission request approval: {str(e)}", exc_info=True)
            error_msg = str(e) if str(e) else "Unknown error occurred"
            flash(f'An error occurred while processing the approval: {error_msg}. Please try again.', 'danger')
            # Ensure url_for is available - it's imported at the top of the file
            try:
                return redirect(url_for('permission.view', id=permission_request.id))
            except Exception as redirect_error:
                logging.error(f"Error redirecting after approval error: {str(redirect_error)}", exc_info=True)
                # Fallback redirect
                return redirect('/permission/')
    
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
        
        # Allow all dates including past dates - no date restriction
        
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
        
        # Allow all dates including past dates - no date restriction
        
        # Create the permission request for the employee
        permission_request = PermissionRequest(
            user_id=employee.id,
            start_time=start_datetime,
            end_time=end_datetime,
            reason=form.reason.data,
            status='approved'  # Auto-approve when created by admin
        )
        
        # Set all approval statuses to approved when created by admin
        permission_request.manager_status = 'approved'
        permission_request.admin_status = 'approved'
        
        db.session.add(permission_request)
        db.session.commit()
        
        # Employee notification removed - will be replaced with SMTP email notifications
        
        # Manager and director notifications removed - will be replaced with SMTP email notifications
        
        flash(f'Permission request for {employee.get_full_name()} has been created and approved successfully!', 'success')
        return redirect(url_for('permission.index'))
    
    return render_template('permission/admin_create.html', 
                          title='Create Permission Request for Employee', 
                          form=form)
