from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFError
from forms import LoginForm, RegistrationForm
from models import db, User, Department, LeaveType, LeaveBalance
from datetime import datetime
from helpers import log_activity
import logging
import os

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = LoginForm()
    
    # Debug: Check Turnstile config
    turnstile_enabled = current_app.config.get('TURNSTILE_ENABLED', False)
    turnstile_site_key = current_app.config.get('TURNSTILE_SITE_KEY', '')
    logging.debug(f'Turnstile config - Enabled: {turnstile_enabled}, Site Key: {turnstile_site_key[:20] if turnstile_site_key else "NOT SET"}')
    
    # When the form is submitted and passes validation
    if request.method == 'POST':
        try:
            # Verify Turnstile if enabled (only in production)
            # Smart detection: Check if we're in production
            is_prod = (not current_app.config.get('DEBUG', True)) or \
                     (os.environ.get('FLASK_ENV', '').lower() == 'production') or \
                     (request.host and 'everlastdashboard.com' in request.host.lower())
            
            if is_prod and current_app.config.get('TURNSTILE_ENABLED'):
                from turnstile_helper import verify_turnstile_token
                turnstile_token = request.form.get('cf-turnstile-response')
                remote_ip = request.remote_addr
                
                is_valid, error_msg = verify_turnstile_token(turnstile_token, remote_ip)
                if not is_valid:
                    flash(f'CAPTCHA verification failed: {error_msg}', 'danger')
                    logging.warning(f'Turnstile verification failed for login attempt from {remote_ip}')
                    return render_template('auth/login.html', form=form, title='Login')
            
            # Validate the form which will include CSRF check
            if form.validate_on_submit():
                # Handle potential duplicate emails - prioritize active users
                users = User.query.filter_by(email=form.email.data).all()
                
                if not users:
                    flash('Login failed. Please check your email and password.', 'danger')
                    logging.warning(f'Login attempt with non-existent email: {form.email.data}')
                else:
                    # Try to find an active user first, then any user
                    user = None
                    for u in users:
                        if u.status == 'active':
                            user = u
                            break
                    
                    # If no active user found, use the first one
                    if not user:
                        user = users[0]
                    
                    # If multiple users found, log a warning
                    if len(users) > 1:
                        logging.warning(f'Multiple users found with email {form.email.data}: IDs {[u.id for u in users]}')
                    
                    # Check password
                    if user and user.password_hash and check_password_hash(user.password_hash, form.password.data):
                        if user.status != 'active':
                            flash('Your account is inactive. Please contact an administrator.', 'danger')
                            return redirect(url_for('auth.login'))
                        
                        remember_me = form.remember.data
                        login_user(user, remember=remember_me)
                        
                        # Store remember me status and login timestamp for session timeout management
                        session['remember_me'] = remember_me
                        session['login_timestamp'] = datetime.utcnow().timestamp()
                        session.permanent = True
                        
                        # Log successful login (IP will be detected from proxy headers if available)
                        log_activity(
                            user=user,
                            action='login',
                            ip_address=None,  # Let log_activity detect real IP from headers
                            description=f'User {user.get_full_name()} logged in successfully'
                        )
                        
                        next_page = request.args.get('next')
                        
                        # Redirect to dashboard based on role
                        if not next_page or not next_page.startswith('/'):
                            return redirect(url_for('dashboard.index'))
                        
                        return redirect(next_page)
                    else:
                        flash('Login failed. Please check your email and password.', 'danger')
                        if user:
                            logging.warning(f'Login failed for user {user.id} ({form.email.data}): password mismatch')
                        else:
                            logging.warning(f'Login failed for email {form.email.data}: no valid user found')
            else:
                # Form validation failed, check if there are form errors to display
                for field, errors in form.errors.items():
                    for error in errors:
                        flash(f"{field}: {error}", 'danger')
        except Exception as e:
            # Catch any other exceptions
            flash(f'An error occurred: {str(e)}', 'danger')
            logging.error(f'Login error: {str(e)}')
    
    # For GET request or if form validation fails
    return render_template('auth/login.html', form=form, title='Login')

@auth_bp.route('/logout')
@login_required
def logout():
    # Log logout before logging out the user (IP will be detected from proxy headers if available)
    user = current_user
    log_activity(
        user=user,
        action='logout',
        ip_address=None,  # Let log_activity detect real IP from headers
        description=f'User {user.get_full_name()} logged out'
    )
    
    # Clear session timeout tracking data
    session.pop('remember_me', None)
    session.pop('login_timestamp', None)
    
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    # Only admins can register new users
    if current_user.role not in ['admin', 'product_owner']:
        flash('You do not have permission to register new users.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    form = RegistrationForm()
    
    # Populate department dropdown
    departments = Department.query.all()
    form.department_id.choices = [(0, 'No Department')] + [(d.id, d.department_name) for d in departments]
    
    # Filter role choices: Admins cannot assign product_owner role
    if current_user.role == 'admin':
        # Remove product_owner from role choices for admins
        form.role.choices = [choice for choice in form.role.choices if choice[0] != 'product_owner']
    
    if form.validate_on_submit():
        # Verify Turnstile if enabled
        if current_app.config.get('TURNSTILE_ENABLED'):
            from turnstile_helper import verify_turnstile_token
            turnstile_token = request.form.get('cf-turnstile-response')
            remote_ip = request.remote_addr
            
            is_valid, error_msg = verify_turnstile_token(turnstile_token, remote_ip)
            if not is_valid:
                flash(f'CAPTCHA verification failed: {error_msg}', 'danger')
                logging.warning(f'Turnstile verification failed for registration attempt from {remote_ip}')
                return render_template('auth/register.html', form=form, title='Register New User', departments=departments)
        
        try:
            # Prevent admins from creating users with product_owner role
            if form.role.data == 'product_owner' and current_user.role == 'admin':
                flash('❌ Access Denied: Only Technical Support can create users with Technical Support role.', 'danger')
                return render_template('auth/register.html', form=form, title='Register New User', departments=departments)
            
            # Check if user with this email already exists
            existing_user = User.query.filter_by(email=form.email.data).first()
            if existing_user:
                flash('A user with that email already exists.', 'danger')
                return render_template('auth/register.html', form=form, title='Register New User')
            
            # Create new user
            hashed_password = generate_password_hash(form.password.data)
            new_user = User(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                password_hash=hashed_password,
                fingerprint_number=form.fingerprint_number.data if form.fingerprint_number.data else None,
                avaya_number=form.avaya_number.data if form.avaya_number.data else None,
                role=form.role.data,
                department_id=form.department_id.data if form.department_id.data != 0 else None,
                status='active',
                joining_date=form.joining_date.data if form.joining_date.data else None,
                # Additional data fields
                date_of_birth=form.date_of_birth.data if form.date_of_birth.data else None,
                phone_number=form.phone_number.data if form.phone_number.data else None,
                alternate_phone_number=form.alternate_phone_number.data if form.alternate_phone_number.data else None,
                position=form.position.data if form.position.data else None,
                salary=form.salary.data if form.salary.data else None,
                currency=form.currency.data if form.currency.data else 'USD'
            )
            
            db.session.add(new_user)
            db.session.commit()

            # Initialize leave balances for the new active user
            current_year = datetime.now().year
            leave_types = LeaveType.query.all()
            for lt in leave_types:
                # Check if a LeaveBalance already exists for this user, leave type, and year
                existing_balance = LeaveBalance.query.filter_by(
                    user_id=new_user.id,
                    leave_type_id=lt.id,
                    year=current_year
                ).first()
                
                if not existing_balance:
                    new_balance = LeaveBalance(
                        user_id=new_user.id,
                        leave_type_id=lt.id,
                        year=current_year,
                        total_days=0,  # Initialize with 0 total days
                        used_days=0,
                        remaining_days=0
                    )
                    db.session.add(new_balance)
            db.session.commit() # Commit the new leave balances

            flash('User registered successfully!', 'success')
            return redirect(url_for('dashboard.users'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering user: {str(e)}', 'danger')
            logging.error(f'Registration error: {str(e)}')
    
    return render_template('auth/register.html', form=form, title='Register New User')
