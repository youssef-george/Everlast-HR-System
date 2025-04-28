from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SelectField, DateField, TimeField, BooleanField, HiddenField, SubmitField, EmailField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp
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
    submit = SubmitField('Register')

class UserEditForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email(), validate_everlast_domain])
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
    submit = SubmitField('Update User')

class ProfileEditForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email', validators=[DataRequired(), Email(), validate_everlast_domain])
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
        if start_date.data < date.today():
            raise ValidationError('Permission requests can only be for present or future dates')
    
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
