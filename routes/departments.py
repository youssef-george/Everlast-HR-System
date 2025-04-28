from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from forms import DepartmentForm
from models import Department, User
from app import db
from helpers import role_required

departments_bp = Blueprint('departments', __name__, url_prefix='/departments')

@departments_bp.route('/')
@login_required
@role_required('admin')
def index():
    """List all departments"""
    departments = Department.query.all()
    
    # Get manager names for each department
    department_data = []
    for dept in departments:
        manager = User.query.get(dept.manager_id) if dept.manager_id else None
        department_data.append({
            'id': dept.id,
            'name': dept.department_name,
            'manager': manager.get_full_name() if manager else 'No Manager Assigned',
            'employee_count': User.query.filter_by(department_id=dept.id).count()
        })
    
    return render_template('departments/index.html', 
                           title='Departments', 
                           departments=department_data)

@departments_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create():
    """Create a new department"""
    form = DepartmentForm()
    
    # Populate manager choices
    managers = User.query.filter(User.role.in_(['manager', 'admin'])).all()
    form.manager_id.choices = [(0, 'No Manager')] + [(m.id, m.get_full_name()) for m in managers]
    
    if form.validate_on_submit():
        department = Department(
            department_name=form.department_name.data,
            manager_id=form.manager_id.data if form.manager_id.data != 0 else None
        )
        
        db.session.add(department)
        db.session.commit()
        
        flash(f'Department {department.department_name} has been created successfully!', 'success')
        return redirect(url_for('departments.index'))
    
    return render_template('departments/edit.html', 
                           title='Create Department', 
                           form=form,
                           is_create=True)

@departments_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit(id):
    """Edit an existing department"""
    department = Department.query.get_or_404(id)
    form = DepartmentForm(obj=department)
    
    # Populate manager choices
    managers = User.query.filter(User.role.in_(['manager', 'admin'])).all()
    form.manager_id.choices = [(0, 'No Manager')] + [(m.id, m.get_full_name()) for m in managers]
    
    if form.validate_on_submit():
        department.department_name = form.department_name.data
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

@departments_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    """Delete a department"""
    department = Department.query.get_or_404(id)
    
    # Check if any employees are in this department
    employees = User.query.filter_by(department_id=id).all()
    if employees:
        flash(f'Cannot delete department. {len(employees)} employees are still assigned to it.', 'danger')
        return redirect(url_for('departments.index'))
    
    db.session.delete(department)
    db.session.commit()
    
    flash(f'Department {department.department_name} has been deleted successfully!', 'success')
    return redirect(url_for('departments.index'))
