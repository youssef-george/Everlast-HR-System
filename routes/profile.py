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
    today = date.today()
    previous_month = (today.replace(day=1) - timedelta(days=1))
    previous_month_days = calendar.monthrange(previous_month.year, previous_month.month)[1]
    
    return render_template('profile/index.html',
                          title='My Profile',
                          today=today,
                          previous_month_days=previous_month_days,
                          timedelta=timedelta)

@profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """Edit user profile"""
    form = ProfileEditForm(obj=current_user)
    
    if form.validate_on_submit():
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
