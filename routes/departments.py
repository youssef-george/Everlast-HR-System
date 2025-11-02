from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from forms import DepartmentForm, DeleteForm
from models import db, Department, User
from helpers import role_required, admin_required

departments_bp = Blueprint('departments', __name__, url_prefix='/departments')

@departments_bp.route('/')
def index():
    departments = Department.query.all()
    delete_form = DeleteForm()
    return render_template('departments/index.html', departments=departments, delete_form=delete_form)

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
