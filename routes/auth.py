from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFError
from forms import LoginForm, RegistrationForm
from models import User, Department
from app import db, app
from datetime import datetime

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = LoginForm()
    
    # When the form is submitted and passes validation
    if request.method == 'POST':
        try:
            # Validate the form which will include CSRF check
            if form.validate_on_submit():
                user = User.query.filter_by(email=form.email.data).first()
                
                if user and check_password_hash(user.password_hash, form.password.data):
                    if user.status != 'active':
                        flash('Your account is inactive. Please contact an administrator.', 'danger')
                        return redirect(url_for('auth.login'))
                    
                    login_user(user, remember=form.remember.data)
                    next_page = request.args.get('next')
                    
                    # Redirect to dashboard based on role
                    if not next_page or not next_page.startswith('/'):
                        return redirect(url_for('dashboard.index'))
                    
                    return redirect(next_page)
                else:
                    flash('Login failed. Please check your email and password.', 'danger')
            else:
                # Form validation failed, check if there are form errors to display
                for field, errors in form.errors.items():
                    for error in errors:
                        flash(f"{field}: {error}", 'danger')
        except Exception as e:
            # Catch any other exceptions
            flash(f'An error occurred: {str(e)}', 'danger')
            app.logger.error(f'Login error: {str(e)}')
    
    # For GET request or if form validation fails
    return render_template('auth/login.html', form=form, title='Login')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    # Only admins can register new users
    if current_user.role != 'admin':
        flash('You do not have permission to register new users.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Redirect to the User Management page
    return redirect(url_for('dashboard.users'))
