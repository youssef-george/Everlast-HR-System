from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, date, timedelta
from models import db, PaidHoliday, User, DailyAttendance
from forms import PaidHolidayForm
import logging

paid_holidays_bp = Blueprint('paid_holidays', __name__)

def role_required(roles):
    """Decorator to require specific roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'danger')
                return redirect(url_for('auth.login'))
            
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@paid_holidays_bp.route('/')
@login_required
@role_required(['admin', 'product_owner', 'director'])
def index():
    """List all paid holidays"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    holidays = PaidHoliday.query.order_by(PaidHoliday.start_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('paid_holidays/index.html', 
                         title='Paid Holidays Management',
                         holidays=holidays)

@paid_holidays_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def create():
    """Create a new paid holiday"""
    form = PaidHolidayForm()
    
    if form.validate_on_submit():
        try:
            holiday = PaidHoliday(
                holiday_type=form.holiday_type.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data if form.holiday_type.data == 'range' else None,
                description=form.description.data,
                is_recurring=form.is_recurring.data,
                created_by=current_user.id
            )
            
            db.session.add(holiday)
            db.session.commit()
            
            # Create daily attendance records for all active employees
            try:
                create_paid_holiday_attendance(holiday)
                flash('Paid holiday created successfully!', 'success')
            except Exception as e:
                logging.error(f'Error creating paid holiday attendance records: {str(e)}')
                flash('Paid holiday created but failed to create attendance records. Please sync manually.', 'warning')
            
            return redirect(url_for('paid_holidays.index'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error creating paid holiday: {str(e)}')
            flash('Error creating paid holiday. Please try again.', 'danger')
    
    return render_template('paid_holidays/create.html', 
                         title='Create Paid Holiday',
                         form=form)

@paid_holidays_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def edit(id):
    """Edit a paid holiday"""
    holiday = PaidHoliday.query.get_or_404(id)
    form = PaidHolidayForm(obj=holiday)
    
    if request.method == 'POST':
        logging.info(f'Form validation errors: {form.errors}')
        logging.info(f'Form data: {request.form}')
        logging.info(f'Form holiday_type: {form.holiday_type.data}')
        logging.info(f'Form start_date: {form.start_date.data}')
        logging.info(f'Form end_date: {form.end_date.data}')
        logging.info(f'Form description: {form.description.data}')
        logging.info(f'Form is_recurring: {form.is_recurring.data}')
    
    if form.validate_on_submit():
        try:
            # Store old dates for updating attendance records
            old_start_date = holiday.start_date
            old_end_date = holiday.end_date
            
            logging.info(f'Updating paid holiday {holiday.id}: {old_start_date} to {form.start_date.data}, {old_end_date} to {form.end_date.data}')
            
            holiday.holiday_type = form.holiday_type.data
            holiday.start_date = form.start_date.data
            holiday.end_date = form.end_date.data if form.holiday_type.data == 'range' else None
            holiday.description = form.description.data
            holiday.is_recurring = form.is_recurring.data
            
            db.session.commit()
            logging.info(f'Successfully updated paid holiday {holiday.id}')
            logging.info(f'New holiday data: {holiday.description}, {holiday.start_date}, {holiday.end_date}, {holiday.holiday_type}, {holiday.is_recurring}')
            
            # Update attendance records if dates or description changed
            if old_start_date != holiday.start_date or old_end_date != holiday.end_date:
                try:
                    update_paid_holiday_attendance(holiday, old_start_date, old_end_date)
                    flash('Paid holiday updated successfully!', 'success')
                except Exception as e:
                    logging.error(f'Error updating paid holiday attendance records: {str(e)}')
                    flash('Paid holiday updated but failed to update attendance records. Please sync manually.', 'warning')
            else:
                # Even if dates didn't change, update the description in attendance records
                try:
                    update_paid_holiday_description(holiday)
                    flash('Paid holiday updated successfully!', 'success')
                except Exception as e:
                    logging.error(f'Error updating paid holiday description in attendance records: {str(e)}')
                    flash('Paid holiday updated but failed to update attendance records. Please sync manually.', 'warning')
            
            return redirect(url_for('paid_holidays.index'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error updating paid holiday: {str(e)}')
            flash('Error updating paid holiday. Please try again.', 'danger')
    else:
        # Form didn't validate
        logging.warning(f'Form validation failed for paid holiday edit. Errors: {form.errors}')
        flash('Please correct the errors below.', 'danger')
    
    return render_template('paid_holidays/edit.html', 
                         title='Edit Paid Holiday',
                         form=form,
                         holiday=holiday)

@paid_holidays_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def delete(id):
    """Delete a paid holiday"""
    holiday = PaidHoliday.query.get_or_404(id)
    
    try:
        # Remove attendance records for this holiday
        remove_paid_holiday_attendance(holiday)
        
        db.session.delete(holiday)
        db.session.commit()
        
        flash('Paid holiday deleted successfully! Attendance data has been updated.', 'success')
        
        # Check if user wants to go to attendance page to see the changes
        if request.args.get('redirect_to') == 'attendance':
            return redirect(url_for('attendance.index', refresh=True))
        
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error deleting paid holiday: {str(e)}')
        flash('Error deleting paid holiday. Please try again.', 'danger')
    
    return redirect(url_for('paid_holidays.index'))

def create_paid_holiday_attendance(holiday):
    """Create daily attendance records for all active employees for the paid holiday"""
    try:
        # Get all active employees
        active_employees = User.query.filter_by(status='active').all()
        
        # Determine date range
        if holiday.holiday_type == 'day':
            dates = [holiday.start_date]
        else:  # range
            dates = []
            current_date = holiday.start_date
            while current_date <= holiday.end_date:
                dates.append(current_date)
                current_date += timedelta(days=1)
        
        # Create attendance records for each employee and date
        for employee in active_employees:
            for holiday_date in dates:
                # Check if attendance record already exists
                existing_attendance = DailyAttendance.query.filter_by(
                    user_id=employee.id,
                    date=holiday_date
                ).first()
                
                if existing_attendance:
                    # Update existing record
                    existing_attendance.status = 'paid_holiday'
                    existing_attendance.is_paid_holiday = True
                    existing_attendance.paid_holiday_id = holiday.id
                    existing_attendance.holiday_name = holiday.description
                    existing_attendance.status_reason = f'Paid Leave - {holiday.description}'
                else:
                    # Create new record
                    attendance = DailyAttendance(
                        user_id=employee.id,
                        date=holiday_date,
                        status='paid_holiday',
                        is_paid_holiday=True,
                        paid_holiday_id=holiday.id,
                        holiday_name=holiday.description,
                        status_reason=f'Paid Leave - {holiday.description}'
                    )
                    db.session.add(attendance)
        
        db.session.commit()
        logging.info(f'Created paid holiday attendance records for {len(active_employees)} employees')
        
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error creating paid holiday attendance: {str(e)}')
        raise

def update_paid_holiday_attendance(holiday, old_start_date, old_end_date):
    """Update attendance records when paid holiday dates change"""
    try:
        # Remove old attendance records
        old_dates = []
        if holiday.holiday_type == 'day':
            old_dates = [old_start_date]
        else:
            current_date = old_start_date
            while current_date <= old_end_date:
                old_dates.append(current_date)
                current_date += timedelta(days=1)
        
        for old_date in old_dates:
            DailyAttendance.query.filter_by(
                paid_holiday_id=holiday.id,
                date=old_date
            ).delete()
        
        # Create new attendance records
        create_paid_holiday_attendance(holiday)
        
        logging.info(f'Updated paid holiday attendance records for holiday {holiday.id}')
        
    except Exception as e:
        logging.error(f'Error updating paid holiday attendance: {str(e)}')
        raise

def update_paid_holiday_description(holiday):
    """Update description in attendance records when paid holiday description changes"""
    try:
        # Update all attendance records for this holiday
        DailyAttendance.query.filter_by(paid_holiday_id=holiday.id).update({
            'holiday_name': holiday.description,
            'status_reason': f'Paid Leave - {holiday.description}'
        })
        db.session.commit()
        
        logging.info(f'Updated paid holiday description in attendance records for holiday {holiday.id}')
        
    except Exception as e:
        logging.error(f'Error updating paid holiday description: {str(e)}')
        raise

def remove_paid_holiday_attendance(holiday):
    """Remove attendance records for a paid holiday"""
    try:
        # Remove all attendance records for this holiday
        DailyAttendance.query.filter_by(paid_holiday_id=holiday.id).delete()
        
        # Also clean up any orphaned records that might have the holiday name but no paid_holiday_id
        DailyAttendance.query.filter(
            DailyAttendance.paid_holiday_id.is_(None),
            DailyAttendance.status == 'paid_holiday',
            DailyAttendance.holiday_name == holiday.description
        ).delete()
        
        db.session.commit()
        
        logging.info(f'Removed paid holiday attendance records for holiday {holiday.id}')
        
    except Exception as e:
        logging.error(f'Error removing paid holiday attendance: {str(e)}')
        raise

@paid_holidays_bp.route('/api/check-conflicts', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner', 'director'])
def check_conflicts():
    """Check for conflicts with existing holidays or leave requests"""
    data = request.get_json()
    start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else start_date
    holiday_id = data.get('holiday_id')  # For edit mode
    
    # Check for overlapping paid holidays
    query = PaidHoliday.query.filter(
        PaidHoliday.start_date <= end_date,
        PaidHoliday.end_date >= start_date
    )
    
    if holiday_id:
        query = query.filter(PaidHoliday.id != holiday_id)
    
    conflicts = query.all()
    
    conflict_data = []
    for conflict in conflicts:
        conflict_data.append({
            'id': conflict.id,
            'description': conflict.description,
            'start_date': conflict.start_date.strftime('%Y-%m-%d'),
            'end_date': conflict.end_date.strftime('%Y-%m-%d') if conflict.end_date else conflict.start_date.strftime('%Y-%m-%d'),
            'type': 'holiday'
        })
    
    return jsonify({
        'has_conflicts': len(conflicts) > 0,
        'conflicts': conflict_data
    })
