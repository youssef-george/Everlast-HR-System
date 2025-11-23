from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from forms import DepartmentForm, DeleteForm
from models import db, Department, User
from helpers import role_required, admin_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

departments_bp = Blueprint('departments', __name__, url_prefix='/departments')

@departments_bp.route('/')
def index():
    departments = Department.query.all()
    delete_form = DeleteForm()
    return render_template('departments/index.html', departments=departments, delete_form=delete_form)

@departments_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner'])
def create():
    """Create a new department"""
    form = DepartmentForm()
    
    # Populate manager choices
    managers = User.query.filter(User.role.in_(['manager', 'admin'])).all()
    form.manager_id.choices = [(0, 'No Manager')] + [(m.id, m.get_full_name()) for m in managers]
    
    if form.validate_on_submit():
        department = Department(
            department_name=form.department_name.data,
            email=form.email.data if form.email.data else None,
            manager_id=form.manager_id.data if form.manager_id.data != 0 else None
        )
        
        db.session.add(department)
        
        try:
            db.session.commit()
            flash(f'Department {department.department_name} has been created successfully!', 'success')
            return redirect(url_for('departments.index'))
        except IntegrityError as e:
            db.session.rollback()
            
            # Check if this is a sequence issue (duplicate key on primary key)
            error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
            if 'duplicate key value violates unique constraint' in error_str and '_pkey' in error_str:
                logger.warning(f"Sequence conflict detected: {error_str}. Attempting to fix sequence...")
                
                try:
                    # Fix the sequence by setting it to max(id) + 1
                    result = db.session.execute(text("SELECT COALESCE(MAX(id), 0) FROM departments"))
                    max_id = result.scalar() or 0
                    next_val = max(max_id, 1)
                    
                    # Reset the sequence
                    db.session.execute(text(f"SELECT setval('departments_id_seq', {next_val}, true)"))
                    db.session.commit()
                    
                    logger.info(f"Sequence fixed: set to {next_val}")
                    
                    # Retry the insertion
                    db.session.add(department)
                    db.session.commit()
                    
                    flash(f'Department {department.department_name} has been created successfully!', 'success')
                    return redirect(url_for('departments.index'))
                except Exception as fix_error:
                    db.session.rollback()
                    logger.error(f"Error fixing sequence: {fix_error}")
                    flash('An error occurred while creating the department. Please try again.', 'danger')
            else:
                # Other integrity errors (e.g., duplicate department name)
                logger.error(f"Integrity error: {error_str}")
                flash('An error occurred while creating the department. It may already exist.', 'danger')
    
    return render_template('departments/edit.html', 
                           title='Create Department', 
                           form=form,
                           is_create=True)

@departments_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'product_owner'])
def edit(id):
    """Edit an existing department"""
    department = Department.query.get_or_404(id)
    form = DepartmentForm(obj=department)
    
    # Populate manager choices
    managers = User.query.filter(User.role.in_(['manager', 'admin'])).all()
    form.manager_id.choices = [(0, 'No Manager')] + [(m.id, m.get_full_name()) for m in managers]
    
    if form.validate_on_submit():
        department.department_name = form.department_name.data
        department.email = form.email.data if form.email.data else None
        department.manager_id = form.manager_id.data if form.manager_id.data != 0 else None
        
        db.session.commit()
        
        flash(f'Department {department.department_name} has been updated successfully!', 'success')
        return redirect(url_for('departments.index'))
    
    # Set default value for manager_id select field
    if department.manager_id:
        form.manager_id.data = department.manager_id
    else:
        form.manager_id.data = 0
    
    return render_template('departments/edit.html', 
                           title='Edit Department', 
                           form=form,
                           department=department,
                           is_create=False)

@departments_bp.route('/departments/delete/<int:dept_id>', methods=['POST'])
@login_required
@admin_required
def delete_department(dept_id):
    form = DeleteForm()
    if form.validate_on_submit():
        department = Department.query.get_or_404(dept_id)
        if department.employees:
            flash('Cannot delete department with assigned employees.', 'danger')
        else:
            db.session.delete(department)
            db.session.commit()
            flash('Department deleted successfully.', 'success')
    else:
        flash('Invalid request or session expired. Please try again.', 'danger')
    return redirect(url_for('departments.index'))
