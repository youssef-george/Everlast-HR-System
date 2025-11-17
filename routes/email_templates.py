from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from forms import EmailTemplateForm
from models import db, EmailTemplate, User
from helpers import role_required, render_email_template
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

email_templates_bp = Blueprint('email_templates', __name__, url_prefix='/dashboard/email-templates')

# Available placeholders for email templates
AVAILABLE_PLACEHOLDERS = {
    'employee_name': 'Employee full name',
    'manager_name': 'Manager full name',
    'admin_name': 'Admin full name',
    'request_type': 'Type of request (Leave Request, Permission Request)',
    'start_date': 'Start date of the request',
    'end_date': 'End date or time range',
    'duration': 'Duration (e.g., "5 day(s)" or "2.5 hour(s)")',
    'reason': 'Reason provided by employee',
    'comment': 'Approval/rejection comment',
    'status': 'Request status (Approved, Rejected, Pending)',
    'request_id': 'Request ID number',
    'approval_link': 'Direct link to approve/reject the request',
    'submission_date': 'Date when request was submitted',
    'submission_time': 'Time when request was submitted'
}


@email_templates_bp.route('/')
@login_required
@role_required('product_owner')
def index():
    """List all email templates"""
    templates = EmailTemplate.query.order_by(EmailTemplate.template_type).all()
    
    # Group templates by type
    template_groups = {}
    for template in templates:
        template_type = template.template_type.split('_')[0]  # 'leave' or 'permission'
        if template_type not in template_groups:
            template_groups[template_type] = []
        template_groups[template_type].append(template)
    
    return render_template('dashboard/email_templates/index.html',
                         templates=templates,
                         template_groups=template_groups,
                         placeholders=AVAILABLE_PLACEHOLDERS)


@email_templates_bp.route('/edit/<int:template_id>', methods=['GET', 'POST'])
@login_required
@role_required('product_owner')
def edit(template_id):
    """Edit an email template"""
    template = EmailTemplate.query.get_or_404(template_id)
    form = EmailTemplateForm(obj=template)
    
    if form.validate_on_submit():
        template.subject = form.subject.data
        template.body_html = form.body_html.data
        template.footer = form.footer.data if form.footer.data else None
        template.signature = form.signature.data if form.signature.data else None
        template.is_active = form.is_active.data
        template.updated_by = current_user.id
        template.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Email template "{template.template_name}" has been updated successfully!', 'success')
        return redirect(url_for('email_templates.index'))
    
    return render_template('dashboard/email_templates/edit.html',
                         form=form,
                         template=template,
                         placeholders=AVAILABLE_PLACEHOLDERS)


@email_templates_bp.route('/preview/<int:template_id>')
@login_required
@role_required('product_owner')
def preview(template_id):
    """Preview email template with sample data"""
    template = EmailTemplate.query.get_or_404(template_id)
    
    # Sample context data for preview
    sample_context = {
        'employee_name': 'John Doe',
        'manager_name': 'Jane Manager',
        'admin_name': 'Admin User',
        'request_type': 'Leave Request',
        'start_date': 'January 15, 2024',
        'end_date': 'January 20, 2024',
        'duration': '5 day(s)',
        'reason': 'Family vacation',
        'comment': 'Approved',
        'status': 'Approved',
        'request_id': '123',
        'approval_link': 'https://example.com/leave/view/123'
    }
    
    # Render template with sample data
    subject, html_body = render_email_template(template, sample_context)
    
    return render_template('dashboard/email_templates/preview.html',
                         template=template,
                         subject=subject,
                         html_body=html_body,
                         sample_context=sample_context)

