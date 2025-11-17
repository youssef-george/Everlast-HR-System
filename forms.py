from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SelectField, DateField, TimeField, BooleanField, HiddenField, SubmitField, EmailField, ValidationError, IntegerField, FileField, DecimalField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, IPAddress, NumberRange
from wtforms.widgets import CheckboxInput, ListWidget
from wtforms.fields import SelectMultipleField
from datetime import datetime, date

# Custom validator for allowed domains
def validate_everlast_domain(form, field):
    allowed_domains = ['@everlastwellness.com', '@gmail.com']
    value = (field.data or '').lower()
    if not any(value.endswith(domain) for domain in allowed_domains):
        raise ValidationError('Only @everlastwellness.com or @gmail.com addresses are allowed.')

class LoginForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email(), validate_everlast_domain])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email(), validate_everlast_domain])
    fingerprint_number = StringField('Fingerprint Number', validators=[Optional(), Length(max=50)])
    avaya_number = StringField('Avaya Number', validators=[Optional(), Length(max=50)])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    department_id = SelectField('Department', coerce=int, validators=[Optional()])
    role = SelectField('Role', choices=[
        ('employee', 'Employee'),
        ('manager', 'Direct Manager'),
        ('admin', 'Account Manager (Admin)'),
        ('product_owner', 'Product Owner'),
        ('director', 'Company Director')
    ], validators=[DataRequired()])
    joining_date = DateField('Joining Date', validators=[Optional()], format='%Y-%m-%d')
    
    # Additional data fields (admin only)
    date_of_birth = DateField('Date of Birth', validators=[Optional()], format='%Y-%m-%d')
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    alternate_phone_number = StringField('Alternate Phone Number', validators=[Optional(), Length(max=20)])
    position = StringField('Position', validators=[Optional(), Length(max=100)])
    salary = DecimalField('Monthly Salary', validators=[Optional()], places=2)
    currency = SelectField('Currency', choices=[
        ('USD', 'USD - US Dollar'),
        ('EUR', 'EUR - Euro'),
        ('GBP', 'GBP - British Pound'),
        ('EGP', 'EGP - Egyptian Pound'),
        ('AED', 'AED - UAE Dirham'),
        ('SAR', 'SAR - Saudi Riyal'),
        ('CAD', 'CAD - Canadian Dollar'),
        ('AUD', 'AUD - Australian Dollar'),
        ('JPY', 'JPY - Japanese Yen'),
        ('CHF', 'CHF - Swiss Franc')
    ], validators=[Optional()], default='USD')
    
    submit = SubmitField('Register')

class UserEditForm(FlaskForm):
    csrf_token = HiddenField(validators=[DataRequired()], render_kw={'id': False})
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    fingerprint_number = StringField('Fingerprint Number', validators=[Optional(), Length(max=50)])
    avaya_number = StringField('Avaya Number', validators=[Optional(), Length(max=50)])
    department_id = SelectField('Department', coerce=int, validators=[Optional()])
    role = SelectField('Role', choices=[
        ('employee', 'Employee'),
        ('manager', 'Direct Manager'),
        ('admin', 'Account Manager (Admin)'),
        ('product_owner', 'Product Owner'),
        ('director', 'Company Director')
    ], validators=[DataRequired()])
    status = SelectField('Status', choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], validators=[DataRequired()])
    joining_date = DateField('Joining Date', validators=[Optional()], format='%Y-%m-%d')
    
    # Additional data fields (admin only)
    date_of_birth = DateField('Date of Birth', validators=[Optional()], format='%Y-%m-%d')
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    alternate_phone_number = StringField('Alternate Phone Number', validators=[Optional(), Length(max=20)])
    position = StringField('Position', validators=[Optional(), Length(max=100)])
    salary = DecimalField('Monthly Salary', validators=[Optional()], places=2)
    currency = SelectField('Currency', choices=[
        ('USD', 'USD - US Dollar'),
        ('EUR', 'EUR - Euro'),
        ('GBP', 'GBP - British Pound'),
        ('EGP', 'EGP - Egyptian Pound'),
        ('AED', 'AED - UAE Dirham'),
        ('SAR', 'SAR - Saudi Riyal'),
        ('CAD', 'CAD - Canadian Dollar'),
        ('AUD', 'AUD - Australian Dollar'),
        ('JPY', 'JPY - Japanese Yen'),
        ('CHF', 'CHF - Swiss Franc')
    ], validators=[Optional()], default='USD')
    
    new_password = PasswordField('New Password', validators=[Optional()])
    confirm_password = PasswordField('Confirm Password', validators=[
        Optional(), EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Update User', render_kw={'id': 'update_user_submit'})

class ProfileEditForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email(), validate_everlast_domain])
    fingerprint_number = StringField('Fingerprint Number', validators=[Optional(), Length(max=50)])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password', validators=[Optional(), Length(min=8, message='Password must be at least 8 characters')])
    confirm_new_password = PasswordField('Confirm New Password', validators=[
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Update Profile')

class DepartmentForm(FlaskForm):
    department_name = StringField('Department Name', validators=[DataRequired(), Length(min=2, max=100)])
    manager_id = SelectField('Department Manager', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Department')

class LeaveRequestForm(FlaskForm):
    leave_type_id = SelectField('Leave Type', coerce=int, validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d')
    reason = TextAreaField('Reason', validators=[DataRequired(), Length(min=5, max=500)])
    delegate_employee_id = SelectField('Delegate Employee', coerce=int, validators=[Optional()])
    submit = SubmitField('Submit Leave Request')
    
    def validate_end_date(self, end_date):
        if end_date.data < self.start_date.data:
            raise ValidationError('End date must be after start date')

class PermissionRequestForm(FlaskForm):
    start_date = DateField('Date', validators=[DataRequired()], format='%Y-%m-%d')
    start_time = TimeField('Start Time', validators=[DataRequired()])
    end_time = TimeField('End Time', validators=[DataRequired()])
    reason = TextAreaField('Reason', validators=[DataRequired(), Length(min=5, max=500)])
    submit = SubmitField('Submit Permission Request')
    
    def validate_start_date(self, start_date):
        # Allow selecting the previous day
        from datetime import timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)
        if start_date.data < yesterday:
            raise ValidationError('Permission requests can only be for yesterday, today, or future dates')
    
    def validate_end_time(self, end_time):
        if self.start_time.data and end_time.data <= self.start_time.data:
            raise ValidationError('End time must be after start time')

class ApprovalForm(FlaskForm):
    status = SelectField('Status', choices=[
        ('approved', 'Approve'),
        ('rejected', 'Reject')
    ], validators=[DataRequired()])
    comment = TextAreaField('Comment', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Submit Decision')

class AdminLeaveRequestForm(LeaveRequestForm):
    """Form for admin to create leave requests on behalf of employees"""
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    delegate_employee_id = SelectField('Delegate Employee', coerce=int, validators=[Optional()])
    submit = SubmitField('Submit Leave Request for Employee')

class UpdateLeaveRequestForm(FlaskForm):
    """Form for updating leave requests with last updated tracking"""
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    leave_type_id = SelectField('Leave Type', coerce=int, validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d')
    reason = TextAreaField('Reason', validators=[DataRequired(), Length(min=5, max=500)])
    delegate_employee_id = SelectField('Delegate Employee', coerce=int, validators=[Optional()])
    status = SelectField('Status', choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], validators=[DataRequired()])
    admin_notes = TextAreaField('Admin Notes', validators=[Length(max=500)])
    submit = SubmitField('Update Leave Request')
    
    def validate_end_date(self, end_date):
        if end_date.data < self.start_date.data:
            raise ValidationError('End date must be after start date')

class AdminPermissionRequestForm(PermissionRequestForm):
    """Form for admin to create permission requests on behalf of employees"""
    employee_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit Permission Request for Employee')

class DeviceSettingsForm(FlaskForm):
    """Form for managing fingerprint device settings"""
    device_ip = StringField('Device IP', validators=[
        DataRequired(),
        IPAddress(message='Please enter a valid IP address')
    ])
    device_port = IntegerField('Device Port', validators=[
        DataRequired(),
        NumberRange(min=1, max=65535, message='Port must be between 1 and 65535')
    ])
    device_name = StringField('Device Name', validators=[
        Optional(),
        Length(max=100, message='Device name must be less than 100 characters')
    ])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Settings')


class DeleteForm(FlaskForm):
    """Generic form for delete operations, primarily for CSRF protection."""
    submit = SubmitField('Delete')

class EmployeeAttachmentForm(FlaskForm):
    """Form for uploading employee attachments"""
    file = FileField('Select File', validators=[DataRequired()])
    display_name = StringField('Display Name', validators=[
        DataRequired(),
        Length(min=1, max=255, message='Display name must be between 1 and 255 characters')
    ])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Upload Attachment', render_kw={'id': 'upload_attachment_submit'})

class LeaveTypeForm(FlaskForm):
    name = StringField('Leave Type Name', validators=[DataRequired(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    color = StringField('Color (Hex)', validators=[DataRequired(), Length(min=7, max=7)], 
                       default='#007bff', render_kw={'placeholder': '#007bff'})
    is_active = BooleanField('Active', default=True)
    requires_balance = BooleanField('Requires Leave Balance', default=False)
    submit = SubmitField('Save Leave Type')

class LeaveBalanceForm(FlaskForm):
    user_id = SelectField('Employee', coerce=int, validators=[DataRequired()])
    leave_type_id = SelectField('Leave Type', coerce=int, validators=[DataRequired()])
    total_days = IntegerField('Total Days', validators=[DataRequired()], default=0)
    used_days = IntegerField('Used Days', validators=[Optional()], default=0)
    manual_remaining_days = IntegerField('Manual Remaining Days (Override)', validators=[Optional()], 
                                       description='Leave empty for automatic calculation')
    year = IntegerField('Year', validators=[DataRequired()], default=lambda: datetime.utcnow().year)
    submit = SubmitField('Save Leave Balance')

class PaidHolidayForm(FlaskForm):
    holiday_type = SelectField('Holiday Type', choices=[
        ('day', 'Single Day'),
        ('range', 'Date Range')
    ], validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[Optional()], format='%Y-%m-%d')
    description = StringField('Holiday Name', validators=[DataRequired(), Length(min=1, max=255)])
    is_recurring = BooleanField('Recurring Holiday (Annual)')
    submit = SubmitField('Save Holiday')
    
    def validate_end_date(self, field):
        if self.holiday_type.data == 'range' and not field.data:
            raise ValidationError('End date is required for date range holidays.')
        
        if field.data and field.data < self.start_date.data:
            raise ValidationError('End date must be after start date.')

class SMTPConfigurationForm(FlaskForm):
    smtp_server = StringField('SMTP Server', validators=[DataRequired(), Length(max=255)], 
                             render_kw={'placeholder': 'e.g., smtp.gmail.com'})
    smtp_port = IntegerField('SMTP Port', validators=[DataRequired(), NumberRange(min=1, max=65535)], 
                            default=587)
    smtp_username = StringField('SMTP Username', validators=[DataRequired(), Length(max=255)], 
                               render_kw={'placeholder': 'your-email@example.com'})
    smtp_password = PasswordField('SMTP Password', validators=[Optional()], 
                                 render_kw={'placeholder': 'Leave blank to keep current password'})
    use_tls = BooleanField('Use TLS', default=True)
    use_ssl = BooleanField('Use SSL', default=False)
    sender_name = StringField('Sender Name', validators=[DataRequired(), Length(max=255)], 
                             default='EverLastERP System')
    sender_email = EmailField('Sender Email', validators=[DataRequired(), Email(), Length(max=255)], 
                             render_kw={'placeholder': 'noreply@yourcompany.com'})
    is_active = BooleanField('Active Configuration', default=True)
    
    # Module-specific email lists
    leave_notification_emails = TextAreaField('Leave Request Notification Emails', 
                                            validators=[Optional()],
                                            render_kw={
                                                'placeholder': 'hr@company.com, manager@company.com, admin@company.com',
                                                'rows': 3,
                                                'class': 'form-control'
                                            })
    permission_notification_emails = TextAreaField('Permission Request Notification Emails', 
                                                  validators=[Optional()],
                                                  render_kw={
                                                      'placeholder': 'supervisor@company.com, hr@company.com',
                                                      'rows': 3,
                                                      'class': 'form-control'
                                                  })
    admin_notification_emails = TextAreaField('Admin Notification Emails', 
                                            validators=[Optional()],
                                            render_kw={
                                                'placeholder': 'admin@company.com, ceo@company.com',
                                                'rows': 3,
                                                'class': 'form-control'
                                            })
    
    # Notification settings
    notify_leave_requests = BooleanField('Enable Leave Request Notifications', default=True)
    notify_permission_requests = BooleanField('Enable Permission Request Notifications', default=True)
    notify_admin_only = BooleanField('Send Only to Custom Email Lists (not all admin users)', default=False)
    
    submit = SubmitField('Save SMTP Configuration')
    test_email = SubmitField('Test Configuration')


class DocumentationPageForm(FlaskForm):
    """Form for creating/editing documentation pages"""
    title = StringField('Title', validators=[DataRequired(), Length(min=1, max=255)])
    content = TextAreaField('Content', validators=[DataRequired()], 
                           render_kw={'rows': 20, 'id': 'doc_content'})
    category = SelectField('Category', validators=[DataRequired()], choices=[
        ('Leave Management', 'Leave Management'),
        ('Permissions', 'Permissions'),
        ('Attendance', 'Attendance'),
        ('Settings', 'Settings'),
        ('Reports', 'Reports'),
        ('General', 'General'),
        ('Getting Started', 'Getting Started'),
        ('Troubleshooting', 'Troubleshooting')
    ])
    tags = StringField('Tags', validators=[Optional()], 
                      render_kw={'placeholder': 'Comma-separated tags (e.g., leave, request, how-to)'})
    visible_roles = SelectMultipleField('Visible to Roles', 
                                       choices=[
                                           ('employee', 'Employee'),
                                           ('manager', 'Manager'),
                                           ('admin', 'Admin'),
                                           ('product_owner', 'Product Owner'),
                                           ('director', 'Director')
                                       ],
                                       validators=[Optional()],
                                       widget=ListWidget(prefix_label=False),
                                       option_widget=CheckboxInput())
    is_published = BooleanField('Publish (uncheck to save as draft)', default=False)
    submit = SubmitField('Save Documentation')
    save_draft = SubmitField('Save as Draft')


class EmailTemplateForm(FlaskForm):
    """Form for creating/editing email templates"""
    template_name = StringField('Template Name', validators=[DataRequired()], 
                               render_kw={'readonly': True})
    subject = StringField('Subject', validators=[DataRequired(), Length(max=255)],
                         render_kw={'placeholder': 'Email subject with placeholders like {employee_name}'})
    body_html = TextAreaField('Email Body (HTML)', validators=[DataRequired()],
                             render_kw={'rows': 20, 'id': 'email_body'})
    footer = TextAreaField('Footer (Optional)', validators=[Optional()],
                          render_kw={'rows': 5, 'placeholder': 'Email footer text with placeholders'})
    signature = TextAreaField('Signature (Optional)', validators=[Optional()],
                             render_kw={'rows': 3, 'placeholder': 'Email signature with placeholders'})
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Template')
