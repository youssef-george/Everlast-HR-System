from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_from_directory, current_app
from flask_login import login_required, current_user
from forms import TicketSubmissionForm, TicketCommentForm, TicketCategoryForm, TicketStatusUpdateForm, TicketEmailTemplateForm
from models import db, Ticket, TicketCategory, TicketDepartmentMapping, TicketComment, TicketAttachment, TicketStatusHistory, TicketEmailTemplate, User, Department
from helpers import role_required, get_tickets_for_user, can_user_view_ticket, can_user_reply_to_ticket, route_ticket_to_departments, send_ticket_created_notification, send_ticket_reply_notification, send_ticket_status_update_notification, send_ticket_resolved_notification
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import logging

logger = logging.getLogger(__name__)

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')

# Allowed file extensions for attachments
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip', 'rar'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_attachment(file, ticket_id, comment_id=None):
    """Save uploaded file and return TicketAttachment object"""
    if not file or file.filename == '':
        return None
    
    if not allowed_file(file.filename):
        raise ValueError(f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}")
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024)}MB")
    
    # Create directory if it doesn't exist
    base_upload = current_app.config.get('UPLOAD_FOLDER', 'attached_assets')
    if os.path.isabs(base_upload):
        upload_dir = os.path.join(base_upload, 'tickets')
    else:
        upload_dir = os.path.join(current_app.root_path, base_upload, 'tickets')
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate secure filename
    filename = secure_filename(file.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"{ticket_id}_{timestamp}_{filename}"
    file_path = os.path.join(upload_dir, filename)
    
    # Save file
    file.save(file_path)
    
    # Create attachment record
    attachment = TicketAttachment(
        ticket_id=ticket_id,
        comment_id=comment_id,
        filename=file.filename,  # Original filename
        file_path=file_path,
        file_size=file_size,
        uploaded_by=current_user.id
    )
    
    return attachment


@tickets_bp.route('/')
@login_required
def index():
    """Employee ticket list - shows only their own tickets"""
    tickets = get_tickets_for_user(current_user, show_own_only=True)
    
    # Filter by status if provided
    status_filter = request.args.get('status', 'all')
    if status_filter != 'all':
        tickets = [t for t in tickets if t.status == status_filter]
    
    # Filter by priority if provided
    priority_filter = request.args.get('priority', 'all')
    if priority_filter != 'all':
        tickets = [t for t in tickets if t.priority == priority_filter]
    
    return render_template('tickets/index.html',
                         title='My Tickets',
                         tickets=tickets,
                         status_filter=status_filter,
                         priority_filter=priority_filter)


@tickets_bp.route('/submit', methods=['GET', 'POST'])
@login_required
def submit():
    """Employee ticket submission"""
    form = TicketSubmissionForm()
    
    # Populate category choices
    categories = TicketCategory.query.filter_by(is_active=True).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if not form.category_id.choices:
        flash('No ticket categories available. Please contact Technical Support.', 'warning')
        return redirect(url_for('tickets.index'))
    
    if form.validate_on_submit():
        try:
            # Create ticket
            ticket = Ticket(
                user_id=current_user.id,
                category_id=form.category_id.data,
                title=form.title.data,
                description=form.description.data,
                priority=form.priority.data,
                status='open'
            )
            
            db.session.add(ticket)
            db.session.flush()  # Get ticket ID
            
            # Handle attachment if provided
            if form.attachment.data:
                try:
                    attachment = save_attachment(form.attachment.data, ticket.id)
                    if attachment:
                        db.session.add(attachment)
                except ValueError as e:
                    flash(f'Attachment error: {str(e)}', 'warning')
            
            db.session.commit()
            
            # Send email notifications
            try:
                send_ticket_created_notification(ticket)
            except Exception as e:
                logger.error(f"Error sending ticket created notification: {str(e)}")
                # Don't fail the ticket creation if email fails
            
            flash('Ticket submitted successfully!', 'success')
            return redirect(url_for('tickets.detail', id=ticket.id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating ticket: {str(e)}", exc_info=True)
            flash('An error occurred while submitting the ticket. Please try again.', 'danger')
    
    return render_template('tickets/submit.html',
                         title='Submit Ticket',
                         form=form)


@tickets_bp.route('/<int:id>')
@login_required
def detail(id):
    """Ticket detail view (role-based)"""
    ticket = Ticket.query.get_or_404(id)
    
    # Check permissions
    if not can_user_view_ticket(current_user, ticket):
        flash('You do not have permission to view this ticket.', 'danger')
        return redirect(url_for('tickets.index'))
    
    # Get comments (filter internal comments for non-authorized users)
    comments = ticket.comments
    if ticket.user_id != current_user.id and current_user.role not in ['product_owner', 'admin', 'director']:
        # IT/Web users can see all comments
        if not (current_user.department_id and 
                current_user.department_id in [d.id for d in ticket.get_assigned_departments()]):
            # Regular users can't see internal comments
            comments = [c for c in comments if not c.is_internal]
    
    # Forms
    comment_form = TicketCommentForm()
    status_form = TicketStatusUpdateForm(obj=ticket)
    
    # Check if user can reply
    can_reply = can_user_reply_to_ticket(current_user, ticket)
    
    # Check if user can update status and see internal comments
    assigned_dept_ids = [d.id for d in ticket.get_assigned_departments()]
    can_update_status = current_user.role in ['product_owner', 'admin', 'director'] or (
        current_user.department_id and current_user.department_id in assigned_dept_ids
    )
    can_see_internal = current_user.role in ['product_owner', 'admin', 'director'] or (
        current_user.department_id and current_user.department_id in assigned_dept_ids
    )
    
    return render_template('tickets/detail.html',
                         title=f'Ticket #{ticket.id}',
                         ticket=ticket,
                         comments=comments,
                         comment_form=comment_form,
                         status_form=status_form,
                         can_reply=can_reply,
                         can_update_status=can_update_status,
                         can_see_internal=can_see_internal)


@tickets_bp.route('/<int:id>/comment', methods=['POST'])
@login_required
def add_comment(id):
    """Add comment/reply to ticket"""
    ticket = Ticket.query.get_or_404(id)
    
    # Check permissions
    if not can_user_reply_to_ticket(current_user, ticket):
        flash('You do not have permission to reply to this ticket.', 'danger')
        return redirect(url_for('tickets.detail', id=id))
    
    form = TicketCommentForm()
    
    if form.validate_on_submit():
        try:
            # Check if user can create internal comments
            assigned_dept_ids = [d.id for d in ticket.get_assigned_departments()]
            can_create_internal = current_user.role in ['product_owner', 'admin', 'director'] or (
                current_user.department_id and current_user.department_id in assigned_dept_ids
            )
            
            comment = TicketComment(
                ticket_id=ticket.id,
                user_id=current_user.id,
                comment_text=form.comment_text.data,
                is_internal=form.is_internal.data if can_create_internal else False
            )
            
            db.session.add(comment)
            db.session.flush()
            
            # Handle attachment if provided
            if form.attachment.data:
                try:
                    attachment = save_attachment(form.attachment.data, ticket.id, comment.id)
                    if attachment:
                        db.session.add(attachment)
                except ValueError as e:
                    flash(f'Attachment error: {str(e)}', 'warning')
            
            # Update ticket updated_at
            ticket.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Send email notifications
            try:
                send_ticket_reply_notification(ticket, comment)
            except Exception as e:
                logger.error(f"Error sending ticket reply notification: {str(e)}")
            
            flash('Comment added successfully!', 'success')
            return redirect(url_for('tickets.detail', id=id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding comment: {str(e)}", exc_info=True)
            flash('An error occurred while adding the comment. Please try again.', 'danger')
    
    return redirect(url_for('tickets.detail', id=id))


@tickets_bp.route('/<int:id>/status', methods=['POST'])
@login_required
def update_status(id):
    """Update ticket status"""
    ticket = Ticket.query.get_or_404(id)
    
    # Check permissions
    assigned_dept_ids = [d.id for d in ticket.get_assigned_departments()]
    can_update = current_user.role in ['product_owner', 'admin', 'director'] or (
        current_user.department_id and current_user.department_id in assigned_dept_ids
    )
    
    if not can_update:
        flash('You do not have permission to update this ticket status.', 'danger')
        return redirect(url_for('tickets.detail', id=id))
    
    form = TicketStatusUpdateForm()
    
    if form.validate_on_submit():
        try:
            old_status = ticket.status
            new_status = form.status.data
            
            # Update ticket status
            ticket.status = new_status
            ticket.updated_at = datetime.utcnow()
            
            # Create status history record
            status_history = TicketStatusHistory(
                ticket_id=ticket.id,
                old_status=old_status,
                new_status=new_status,
                changed_by=current_user.id,
                comment=form.comment.data if form.comment.data else None
            )
            
            db.session.add(status_history)
            db.session.commit()
            
            # Send email notifications
            try:
                send_ticket_status_update_notification(ticket, old_status, new_status)
                
                # Send resolved/closed notification if applicable
                if new_status in ['resolved', 'closed']:
                    send_ticket_resolved_notification(ticket)
            except Exception as e:
                logger.error(f"Error sending ticket status notification: {str(e)}")
            
            flash(f'Ticket status updated to {new_status.replace("_", " ").title()}!', 'success')
            return redirect(url_for('tickets.detail', id=id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating ticket status: {str(e)}", exc_info=True)
            flash('An error occurred while updating the ticket status. Please try again.', 'danger')
    
    return redirect(url_for('tickets.detail', id=id))


@tickets_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('product_owner')
def delete_ticket(id):
    """Delete a ticket - Technical Support only"""
    ticket = Ticket.query.get_or_404(id)
    
    try:
        # Delete physical attachment files
        for attachment in ticket.attachments:
            if attachment.file_path and os.path.exists(attachment.file_path):
                try:
                    os.remove(attachment.file_path)
                    logger.info(f"Deleted attachment file: {attachment.file_path}")
                except Exception as e:
                    logger.warning(f"Could not delete attachment file {attachment.file_path}: {str(e)}")
        
        # Delete comment attachments
        for comment in ticket.comments:
            for attachment in comment.attachments:
                if attachment.file_path and os.path.exists(attachment.file_path):
                    try:
                        os.remove(attachment.file_path)
                        logger.info(f"Deleted comment attachment file: {attachment.file_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete comment attachment file {attachment.file_path}: {str(e)}")
        
        ticket_id = ticket.id
        ticket_title = ticket.title
        
        # Delete ticket (cascade will handle related records)
        db.session.delete(ticket)
        db.session.commit()
        
        logger.info(f"Technical Support {current_user.id} deleted ticket #{ticket_id}: {ticket_title}")
        flash(f'Ticket #{ticket_id} "{ticket_title}" deleted successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting ticket {id}: {str(e)}", exc_info=True)
        flash('An error occurred while deleting the ticket. Please try again.', 'danger')
    
    # Redirect Technical Support to manager dashboard, others to their ticket list
    if current_user.role == 'product_owner':
        return redirect(url_for('tickets.manager'))
    return redirect(url_for('tickets.index'))


@tickets_bp.route('/inbox')
@login_required
def inbox():
    """IT/Web department inbox - shows all tickets assigned to user's department"""
    # Check if user is in IT/Web department
    if not current_user.department_id:
        flash('You are not assigned to a department that handles tickets.', 'warning')
        return redirect(url_for('tickets.index'))
    
    # Get tickets for user's department
    tickets = get_tickets_for_user(current_user)
    
    # Apply filters
    status_filter = request.args.get('status', 'all')
    if status_filter != 'all':
        tickets = [t for t in tickets if t.status == status_filter]
    
    priority_filter = request.args.get('priority', 'all')
    if priority_filter != 'all':
        tickets = [t for t in tickets if t.priority == priority_filter]
    
    category_filter = request.args.get('category', 'all')
    if category_filter != 'all':
        try:
            category_id = int(category_filter)
            tickets = [t for t in tickets if t.category_id == category_id]
        except ValueError:
            pass
    
    # Get department name
    department = Department.query.get(current_user.department_id)
    department_name = department.department_name if department else 'Unknown'
    
    return render_template('tickets/inbox.html',
                         title='Ticket Inbox',
                         tickets=tickets,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         category_filter=category_filter,
                         department_name=department_name)


@tickets_bp.route('/manager')
@login_required
@role_required('product_owner', 'admin')
def manager():
    """Technical Support and Admin ticket manager dashboard"""
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    
    # Statistics
    stats = {
        'total': len(tickets),
        'open': len([t for t in tickets if t.status == 'open']),
        'in_progress': len([t for t in tickets if t.status == 'in_progress']),
        'resolved': len([t for t in tickets if t.status == 'resolved']),
        'closed': len([t for t in tickets if t.status == 'closed']),
        'critical': len([t for t in tickets if t.priority == 'critical']),
        'high': len([t for t in tickets if t.priority == 'high']),
    }
    
    # Apply filters
    status_filter = request.args.get('status', 'all')
    if status_filter != 'all':
        tickets = [t for t in tickets if t.status == status_filter]
    
    priority_filter = request.args.get('priority', 'all')
    if priority_filter != 'all':
        tickets = [t for t in tickets if t.priority == priority_filter]
    
    return render_template('tickets/manager.html',
                         title='Ticketing Manager',
                         tickets=tickets,
                         stats=stats,
                         status_filter=status_filter,
                         priority_filter=priority_filter)


@tickets_bp.route('/categories')
@login_required
@role_required('product_owner')
def categories():
    """Technical Support category management"""
    categories = TicketCategory.query.order_by(TicketCategory.name).all()
    return render_template('tickets/categories.html',
                         title='Ticket Categories',
                         categories=categories)


@tickets_bp.route('/categories/create', methods=['GET', 'POST'])
@login_required
@role_required('product_owner')
def create_category():
    """Create new ticket category"""
    form = TicketCategoryForm()
    
    # Populate department choices
    departments = Department.query.all()
    form.departments.choices = [(d.id, d.department_name) for d in departments]
    
    if form.validate_on_submit():
        try:
            category = TicketCategory(
                name=form.name.data,
                description=form.description.data,
                is_active=form.is_active.data
            )
            
            db.session.add(category)
            db.session.flush()
            
            # Create department mappings
            if form.departments.data:
                for dept_id in form.departments.data:
                    mapping = TicketDepartmentMapping(
                        category_id=category.id,
                        department_id=dept_id
                    )
                    db.session.add(mapping)
            
            db.session.commit()
            
            flash(f'Category "{category.name}" created successfully!', 'success')
            return redirect(url_for('tickets.categories'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating category: {str(e)}", exc_info=True)
            flash('An error occurred while creating the category. Please try again.', 'danger')
    
    return render_template('tickets/category_form.html',
                         title='Create Category',
                         form=form,
                         is_edit=False)


@tickets_bp.route('/categories/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('product_owner')
def edit_category(id):
    """Edit ticket category"""
    category = TicketCategory.query.get_or_404(id)
    form = TicketCategoryForm()
    
    # Populate department choices (must be done before form processing)
    departments = Department.query.all()
    form.departments.choices = [(d.id, d.department_name) for d in departments]
    
    if request.method == 'GET':
        # Populate form with existing category data
        form.name.data = category.name
        form.description.data = category.description
        form.is_active.data = category.is_active
        
        # Set current department mappings
        current_mappings = TicketDepartmentMapping.query.filter_by(category_id=category.id).all()
        form.departments.data = [m.department_id for m in current_mappings]
    
    if form.validate_on_submit():
        try:
            category.name = form.name.data
            category.description = form.description.data if form.description.data else None
            category.is_active = form.is_active.data
            category.updated_at = datetime.utcnow()
            
            # Update department mappings
            TicketDepartmentMapping.query.filter_by(category_id=category.id).delete()
            db.session.flush()  # Ensure delete is processed before adding new ones
            
            if form.departments.data:
                for dept_id in form.departments.data:
                    mapping = TicketDepartmentMapping(
                        category_id=category.id,
                        department_id=dept_id
                    )
                    db.session.add(mapping)
            
            db.session.commit()
            
            flash(f'Category "{category.name}" updated successfully!', 'success')
            return redirect(url_for('tickets.categories'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating category: {str(e)}", exc_info=True)
            flash(f'An error occurred while updating the category: {str(e)}', 'danger')
    elif request.method == 'POST':
        # Form validation failed - re-populate department choices
        current_mappings = TicketDepartmentMapping.query.filter_by(category_id=category.id).all()
        if not form.departments.data:
            form.departments.data = [m.department_id for m in current_mappings]
    
    return render_template('tickets/category_form.html',
                         title='Edit Category',
                         form=form,
                         category=category,
                         is_edit=True)


@tickets_bp.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
@role_required('product_owner')
def delete_category(id):
    """Delete ticket category - Technical Support can delete any category"""
    category = TicketCategory.query.get_or_404(id)
    
    # Technical Support can delete categories even if they have tickets
    # When category is deleted, tickets will have category_id set to NULL (due to ondelete='SET NULL')
    ticket_count = Ticket.query.filter_by(category_id=category.id).count()
    
    try:
        category_name = category.name
        db.session.delete(category)
        db.session.commit()
        
        if ticket_count > 0:
            flash(f'Category "{category_name}" deleted successfully! {ticket_count} ticket(s) are now uncategorized.', 'success')
        else:
            flash(f'Category "{category_name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting category: {str(e)}", exc_info=True)
        flash('An error occurred while deleting the category. Please try again.', 'danger')
    
    return redirect(url_for('tickets.categories'))


@tickets_bp.route('/email-templates')
@login_required
@role_required('product_owner')
def email_templates():
    """Technical Support email template management"""
    templates = TicketEmailTemplate.query.order_by(TicketEmailTemplate.template_type).all()
    
    # Template types that should exist
    required_types = ['ticket_created_requester', 'ticket_created_department', 'ticket_reply', 'ticket_status_update', 'ticket_resolved', 'ticket_closed']
    existing_types = [t.template_type for t in templates]
    
    # Create missing templates with defaults
    for template_type in required_types:
        if template_type not in existing_types:
            default_template = TicketEmailTemplate(
                template_type=template_type,
                subject=get_default_template_subject(template_type),
                body_html=get_default_template_body(template_type),
                is_active=True
            )
            db.session.add(default_template)
    
    if any(template_type not in existing_types for template_type in required_types):
        db.session.commit()
        templates = TicketEmailTemplate.query.order_by(TicketEmailTemplate.template_type).all()
    
    return render_template('tickets/email_templates.html',
                         title='Ticket Email Templates',
                         templates=templates)


@tickets_bp.route('/email-templates/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('product_owner')
def edit_email_template(id):
    """Edit ticket email template"""
    template = TicketEmailTemplate.query.get_or_404(id)
    form = TicketEmailTemplateForm(obj=template)
    
    if form.validate_on_submit():
        try:
            template.subject = form.subject.data
            template.body_html = form.body_html.data
            template.is_active = form.is_active.data
            template.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            flash(f'Email template "{template.template_type}" updated successfully!', 'success')
            return redirect(url_for('tickets.email_templates'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating email template: {str(e)}", exc_info=True)
            flash('An error occurred while updating the email template. Please try again.', 'danger')
    
    return render_template('tickets/email_template_form.html',
                         title='Edit Email Template',
                         form=form,
                         template=template)


@tickets_bp.route('/attachment/<int:id>')
@login_required
def download_attachment(id):
    """Download ticket attachment"""
    attachment = TicketAttachment.query.get_or_404(id)
    
    # Check permissions
    ticket = attachment.ticket
    if not can_user_view_ticket(current_user, ticket):
        flash('You do not have permission to access this attachment.', 'danger')
        return redirect(url_for('tickets.index'))
    
    # Get directory and filename
    # Handle both absolute and relative paths
    if os.path.isabs(attachment.file_path):
        directory = os.path.dirname(attachment.file_path)
        filename = os.path.basename(attachment.file_path)
    else:
        directory = os.path.join(current_app.root_path, os.path.dirname(attachment.file_path))
        filename = os.path.basename(attachment.file_path)
    
    return send_from_directory(directory, filename, as_attachment=True, download_name=attachment.filename)


def get_default_template_subject(template_type):
    """Get default email template subject"""
    defaults = {
        'ticket_created_requester': 'Ticket Created: {ticket_title}',
        'ticket_created_department': 'New Ticket Assigned to {department_name} Team: {ticket_title}',
        'ticket_reply': 'New Reply on Ticket #{ticket_id}: {ticket_title}',
        'ticket_status_update': 'Ticket #{ticket_id} Status Updated: {ticket_title}',
        'ticket_resolved': 'Ticket #{ticket_id} Resolved: {ticket_title}',
        'ticket_closed': 'Ticket #{ticket_id} Closed: {ticket_title}'
    }
    return defaults.get(template_type, 'Ticket Notification')


def get_default_template_body(template_type):
    """Get default email template body"""
    defaults = {
        'ticket_created_requester': '''
        <h2>Ticket Created Successfully</h2>
        <p>Hello {requester_name},</p>
        <p>You have an open ticket:</p>
        <ul>
            <li><strong>Ticket ID:</strong> #{ticket_id}</li>
            <li><strong>Title:</strong> {ticket_title}</li>
            <li><strong>Category:</strong> {category_name}</li>
            <li><strong>Priority:</strong> {priority}</li>
            <li><strong>Status:</strong> {status}</li>
            <li><strong>Created:</strong> {created_at}</li>
        </ul>
        <p>Your ticket has been assigned to the appropriate department and will be reviewed soon.</p>
        <p><a href="{ticket_url}">View Your Ticket</a></p>
        ''',
        'ticket_created_department': '''
        <h2>New Ticket Assigned</h2>
        <p>Hello {department_name} team,</p>
        <p><strong>{requester_name}</strong> has submitted a new ticket with the following details:</p>
        <ul>
            <li><strong>Requester:</strong> {requester_name}</li>
            <li><strong>Ticket ID:</strong> #{ticket_id}</li>
            <li><strong>Title:</strong> {ticket_title}</li>
            <li><strong>Category:</strong> {category_name}</li>
            <li><strong>Priority:</strong> {priority}</li>
            <li><strong>Status:</strong> {status}</li>
            <li><strong>Created:</strong> {created_at}</li>
        </ul>
        <p><strong>Description:</strong></p>
        <p>{description}</p>
        <p><a href="{ticket_url}">View and Respond to Ticket</a></p>
        ''',
        'ticket_reply': '''
        <h2>New Reply on Ticket</h2>
        <p>Hello {requester_name},</p>
        <p>A new reply has been added to ticket #{ticket_id}:</p>
        <p><strong>Reply from:</strong> {commenter_name}</p>
        <p><strong>Comment:</strong></p>
        <p>{comment_text}</p>
        <p><a href="{ticket_url}">View Ticket</a></p>
        ''',
        'ticket_status_update': '''
        <h2>Ticket Status Updated</h2>
        <p>Hello {requester_name},</p>
        <p>The status of ticket #{ticket_id} has been updated:</p>
        <p><strong>Status changed from:</strong> {old_status}</p>
        <p><strong>Status changed to:</strong> {new_status}</p>
        <p><a href="{ticket_url}">View Ticket</a></p>
        ''',
        'ticket_resolved': '''
        <h2>Ticket Resolved</h2>
        <p>Hello {requester_name},</p>
        <p>Your ticket #{ticket_id} has been resolved:</p>
        <p><strong>Title:</strong> {ticket_title}</p>
        <p><a href="{ticket_url}">View Ticket</a></p>
        ''',
        'ticket_closed': '''
        <h2>Ticket Closed</h2>
        <p>Hello {requester_name},</p>
        <p>Your ticket #{ticket_id} has been closed:</p>
        <p><strong>Title:</strong> {ticket_title}</p>
        <p><a href="{ticket_url}">View Ticket</a></p>
        '''
    }
    return defaults.get(template_type, '<p>Ticket Notification</p>')

