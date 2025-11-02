from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SelectField, DateField, TimeField, BooleanField, HiddenField, SubmitField, EmailField, ValidationError, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, IPAddress, NumberRange
from datetime import datetime, date

# Custom validator for @everlastwellness.com domain
def validate_everlast_domain(form, field):
    if not field.data.endswith('@everlastwellness.com'):
        raise ValidationError('Only @everlastwellness.com email addresses are allowed.')

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
        ('director', 'Company Director')
    ], validators=[DataRequired()])
    joining_date = DateField('Joining Date', validators=[Optional()], format='%Y-%m-%d')
    submit = SubmitField('Register')

class UserEditForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email(), validate_everlast_domain])
    fingerprint_number = StringField('Fingerprint Number', validators=[Optional(), Length(max=50)])
    avaya_number = StringField('Avaya Number', validators=[Optional(), Length(max=50)])
    department_id = SelectField('Department', coerce=int, validators=[Optional()])
    role = SelectField('Role', choices=[
        ('employee', 'Employee'),
        ('manager', 'Direct Manager'),
        ('admin', 'Account Manager (Admin)'),
        ('director', 'Company Director')
    ], validators=[DataRequired()])
    status = SelectField('Status', choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], validators=[DataRequired()])
    joining_date = DateField('Joining Date', validators=[Optional()], format='%Y-%m-%d')
    new_password = PasswordField('New Password', validators=[Optional(), Length(min=8, message='Password must be at least 8 characters')])
    confirm_password = PasswordField('Confirm Password', validators=[
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Update User')

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
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d')
    reason = TextAreaField('Reason', validators=[DataRequired(), Length(min=5, max=500)])
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
    submit = SubmitField('Submit Leave Request for Employee')

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
    submit = SubmitField('Save Settings')

class DeleteForm(FlaskForm):
    """Generic form for delete operations, primarily for CSRF protection."""
    submit = SubmitField('Delete')
