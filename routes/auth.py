from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFError
from forms import LoginForm, RegistrationForm
from models import db, User, Department
from datetime import datetime
import logging

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
                try:
                    user = User.query.filter_by(email=form.email.data).first()
                except Exception as e:
                    logging.error(f'Database error during login query: {str(e)}', exc_info=True)
                    flash('Database connection error. Please try again.', 'danger')
                    return render_template('auth/login.html', form=form, title='Login')
                
                if user and check_password_hash(user.password_hash, form.password.data):
                    if user.status != 'active':
                        flash('Your account is inactive. Please contact an administrator.', 'danger')
                        return redirect(url_for('auth.login'))
                    
                    try:
                        # Login the user
                        login_result = login_user(user, remember=form.remember.data)
                        logging.info(f'User {user.email} logged in successfully. Login result: {login_result}')
                        
                        # Force session save
                        from flask import session as flask_session
                        flask_session.permanent = True
                        
                        next_page = request.args.get('next')
                        
                        # Redirect to dashboard based on role
                        if not next_page or not next_page.startswith('/'):
                            logging.info(f'Redirecting user {user.email} to dashboard')
                            return redirect(url_for('dashboard.index'))
                        
                        logging.info(f'Redirecting user {user.email} to {next_page}')
                        return redirect(next_page)
                    except Exception as e:
                        logging.error(f'Error during login_user call: {str(e)}', exc_info=True)
                        flash('An error occurred during login. Please try again.', 'danger')
                        return render_template('auth/login.html', form=form, title='Login')
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
            logging.error(f'Login error: {str(e)}')
    
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
    if current_user.role not in ['admin', 'product_owner']:
        flash('You do not have permission to register new users.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    form = RegistrationForm()
    
    # Populate department dropdown
    departments = Department.query.all()
    form.department_id.choices = [(0, 'No Department')] + [(d.id, d.department_name) for d in departments]
    
    if form.validate_on_submit():
        try:
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
            leave_types = models.LeaveType.query.all()
            for lt in leave_types:
                # Check if a LeaveBalance already exists for this user, leave type, and year
                existing_balance = models.LeaveBalance.query.filter_by(
                    user_id=new_user.id,
                    leave_type_id=lt.id,
                    year=current_year
                ).first()
                
                if not existing_balance:
                    new_balance = models.LeaveBalance(
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
