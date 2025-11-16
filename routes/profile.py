from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from forms import ProfileEditForm
from models import db, User
from datetime import datetime, date, timedelta
import calendar

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')

@profile_bp.route('/')
@login_required
def index():
    """Show user profile"""
    from models import LeaveBalance, LeaveType
    from datetime import datetime
    
    today = date.today()
    previous_month = (today.replace(day=1) - timedelta(days=1))
    previous_month_days = calendar.monthrange(previous_month.year, previous_month.month)[1]
    
    # Get attendance statistics for current and previous month
    current_month_stats = current_user.get_attendance_stats(today.year, today.month)
    previous_month_stats = current_user.get_attendance_stats(previous_month.year, previous_month.month)
    
    # Get leave balances for current year
    current_year = datetime.now().year
    leave_balances = LeaveBalance.query.join(LeaveType).filter(
        LeaveBalance.user_id == current_user.id,
        LeaveBalance.year == current_year
    ).all()
    
    return render_template('profile/index.html',
                          title='My Profile',
                          today=today,
                          previous_month_days=previous_month_days,
                          timedelta=timedelta,
                          current_month_stats=current_month_stats,
                          previous_month_stats=previous_month_stats,
                          leave_balances=leave_balances)

@profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """Edit user profile"""
    form = ProfileEditForm(obj=current_user)
    
    if form.validate_on_submit():
        # Only admins and product owners can edit profiles and change passwords
        if current_user.role not in ['admin', 'product_owner']:
            # Employees cannot change their password or profile information
            flash('You do not have permission to update your profile. Please contact an administrator.', 'warning')
            return redirect(url_for('profile.index'))
        
        # For admins and product owners, allow full profile updates
        else:
            # Check if email is being changed and if it's already taken
            if form.email.data != current_user.email:
                existing_user = User.query.filter_by(email=form.email.data).first()
                if existing_user:
                    flash('That email is already taken. Please choose a different one.', 'danger')
                    return render_template('profile/edit.html', title='Edit Profile', form=form)
            
            # Update basic profile information
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.email = form.email.data
            current_user.fingerprint_number = form.fingerprint_number.data if form.fingerprint_number.data else None
            
            # Update password if provided
            if form.new_password.data:
                # Prevent password changes for protected accounts
                protected_emails = ['youssef.george0458@gmail.com', 'erp@everlastwellness.com']
                if current_user.email.lower() in [email.lower() for email in protected_emails]:
                    flash('Password change is not allowed for this account. Please contact system administrator.', 'danger')
                    return render_template('profile/edit.html', title='Edit Profile', form=form)
                
                if not form.current_password.data:
                    flash('Current password is required to set a new password.', 'danger')
                    return render_template('profile/edit.html', title='Edit Profile', form=form)
                
                if not check_password_hash(current_user.password_hash, form.current_password.data):
                    flash('Current password is incorrect.', 'danger')
                    return render_template('profile/edit.html', title='Edit Profile', form=form)
                
                current_user.password_hash = generate_password_hash(form.new_password.data)
            
            db.session.commit()
            flash('Your profile has been updated successfully!', 'success')
            return redirect(url_for('profile.index'))
    
    return render_template('profile/edit.html', 
                           title='Edit Profile', 
                           form=form)
