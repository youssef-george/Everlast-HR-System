from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date
from forms import NoteForm
from models import db, Note, User
from helpers import role_required, get_employees_for_manager, log_activity
from sqlalchemy import or_, and_
import logging

notes_bp = Blueprint('notes', __name__, url_prefix='/notes')

@notes_bp.route('/')
@login_required
def index():
    """List notes based on user role and view parameter"""
    user_role = current_user.role
    notes = []
    view_type = request.args.get('view', None)
    page_title = 'Notes'
    
    if user_role == 'employee':
        # Employees see only their own notes
        notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
    
    elif user_role == 'manager':
        if view_type == 'my':
            # Show only the manager's own notes
            page_title = 'My Notes'
            notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
        else:
            # Show team notes (default view for managers)
            page_title = 'Team Notes'
            # Get employees from all departments managed by this manager
            managed_dept_ids = [dept.id for dept in current_user.managed_department]
            if managed_dept_ids:
                notes = Note.query.join(
                    User, Note.user_id == User.id
                ).filter(
                    User.department_id.in_(managed_dept_ids)
                ).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
            else:
                # If no managed departments, show only own notes
                notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
    
    elif user_role == 'product_owner':
        # Technical Support see all notes
        if view_type == 'my':
            page_title = 'My Notes'
            notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
        else:
            page_title = 'All Notes'
            notes = Note.query.order_by(Note.start_date.desc(), Note.created_at.desc()).all()
    
    elif user_role == 'admin':
        if view_type == 'my':
            page_title = 'My Notes'
            notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
        elif view_type == 'all':
            page_title = 'All Notes'
            notes = Note.query.order_by(Note.start_date.desc(), Note.created_at.desc()).all()
        else:
            # Show notes for assigned departments
            page_title = 'Department Notes'
            if current_user.managed_department:
                admin_dept_ids = [dept.id for dept in current_user.managed_department]
                notes = Note.query.join(
                    User, Note.user_id == User.id
                ).filter(
                    User.department_id.in_(admin_dept_ids)
                ).order_by(Note.start_date.desc(), Note.created_at.desc()).all()
            else:
                notes = Note.query.order_by(Note.start_date.desc(), Note.created_at.desc()).all()
    
    elif user_role == 'director':
        # Directors see all notes
        page_title = 'All Company Notes'
        notes = Note.query.order_by(Note.start_date.desc(), Note.created_at.desc()).all()
    
    # Add pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    notes_paginated = notes[(page-1)*per_page:page*per_page]
    total_pages = (len(notes) + per_page - 1) // per_page
    
    # Get departments for filter dropdown
    from models import Department
    departments = Department.query.all()
    
    return render_template('notes/index.html',
                          title=page_title,
                          notes=notes_paginated,
                          view_type=view_type,
                          total_pages=total_pages,
                          current_page=page,
                          total_records=len(notes),
                          departments=departments)

@notes_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create a new note"""
    form = NoteForm()
    
    # Initialize choices to empty lists
    form.employee_id.choices = []
    
    # Populate employee dropdown based on role
    if current_user.role == 'employee':
        # Employees can only create notes for themselves
        form.employee_id.choices = [(current_user.id, current_user.get_full_name())]
        form.employee_id.data = current_user.id
    elif current_user.role == 'manager':
        # Managers see only employees in their department or who report to them
        try:
            department_employees = User.query.filter(
                User.status == 'active',
                User.department_id == current_user.department_id,
                User.id != current_user.id,
                ~User.first_name.like('User%'),
                ~User.first_name.like('NN-%'),
                User.first_name != '',
                User.last_name != ''
            )
            
            reporting_employees = User.query.filter(
                User.status == 'active',
                User.manager_id == current_user.id,
                User.id != current_user.id,
                ~User.first_name.like('User%'),
                ~User.first_name.like('NN-%'),
                User.first_name != '',
                User.last_name != ''
            )
            
            employees = department_employees.union(reporting_employees).order_by(User.first_name).all()
            
            # Add manager themselves
            employee_choices = [(current_user.id, current_user.get_full_name())]
            for employee in employees:
                dept_name = employee.department.department_name if employee.department else "No Department"
                display_text = f"{employee.get_full_name()} ({dept_name})"
                employee_choices.append((employee.id, display_text))
            
            form.employee_id.choices = employee_choices
        except Exception as e:
            current_app.logger.error(f"Error fetching employees for manager: {e}")
            form.employee_id.choices = [(current_user.id, current_user.get_full_name())]
    elif current_user.managed_department:
        # If admin/product_owner is assigned to specific departments
        admin_dept_ids = [dept.id for dept in current_user.managed_department]
        employees = User.query.filter(
            User.status == 'active',
            User.department_id.in_(admin_dept_ids),
            ~User.first_name.like('User%'),
            ~User.first_name.like('NN-%'),
            User.first_name != '',
            User.last_name != ''
        ).order_by(User.first_name).all()
        
        employee_choices = []
        for employee in employees:
            dept_name = employee.department.department_name if employee.department else "No Department"
            display_text = f"{employee.get_full_name()} ({dept_name})"
            employee_choices.append((employee.id, display_text))
        
        form.employee_id.choices = employee_choices
    else:
        # Admins/product_owners see all active employees
        employees = User.query.filter(
            User.status == 'active',
            ~User.first_name.like('User%'),
            ~User.first_name.like('NN-%'),
            User.first_name != '',
            User.last_name != ''
        ).order_by(User.first_name).all()
        
        employee_choices = []
        for employee in employees:
            dept_name = employee.department.department_name if employee.department else "No Department"
            display_text = f"{employee.get_full_name()} ({dept_name})"
            employee_choices.append((employee.id, display_text))
        
        form.employee_id.choices = employee_choices
    
    if form.validate_on_submit():
        # Determine which employee the note is for
        if current_user.role == 'employee':
            employee_id = current_user.id
        else:
            employee_id = form.employee_id.data
        
        employee = User.query.get(employee_id)
        if not employee:
            flash('Selected employee does not exist.', 'danger')
            return redirect(url_for('notes.create'))
        
        # Validate manager authorization if manager is creating note
        if current_user.role == 'manager' and employee_id != current_user.id:
            is_in_department = (employee.department_id == current_user.department_id)
            is_direct_report = (employee.manager_id == current_user.id)
            
            if not (is_in_department or is_direct_report):
                flash('You can only create notes for your team members.', 'danger')
                return redirect(url_for('notes.create'))
        
        note = Note(
            user_id=employee_id,
            created_by_id=current_user.id,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            comment=form.comment.data
        )
        
        db.session.add(note)
        db.session.commit()
        
        # Log note creation
        date_range = f"{form.start_date.data.strftime('%Y-%m-%d')}"
        if form.start_date.data != form.end_date.data:
            date_range = f"{form.start_date.data.strftime('%Y-%m-%d')} to {form.end_date.data.strftime('%Y-%m-%d')}"
        
        log_activity(
            user=current_user,
            action='create_note',
            entity_type='note',
            entity_id=note.id,
            before_values=None,
            after_values={
                'user_id': employee_id,
                'employee_name': employee.get_full_name(),
                'date_range': date_range,
                'comment': form.comment.data[:100] if len(form.comment.data) > 100 else form.comment.data
            },
            description=f'User {current_user.get_full_name()} created a note for {employee.get_full_name()} ({date_range})'
        )
        
        flash('Note created successfully!', 'success')
        return redirect(url_for('notes.index'))
    
    return render_template('notes/create.html',
                          title='Create Note',
                          form=form)

@notes_bp.route('/view/<int:id>')
@login_required
def view(id):
    """View a note"""
    note = Note.query.get_or_404(id)
    
    # Check if user has permission to view this note
    user_role = current_user.role
    if user_role == 'employee' and note.user_id != current_user.id:
        flash('You do not have permission to view this note.', 'danger')
        return redirect(url_for('notes.index'))
    
    # Check manager access
    if user_role == 'manager':
        if note.user_id != current_user.id:
            user = User.query.get(note.user_id)
            if user:
                managed_dept_ids = [dept.id for dept in current_user.managed_department]
                if user.department_id not in managed_dept_ids:
                    flash('You do not have permission to view this note.', 'danger')
                    return redirect(url_for('notes.index'))
    
    return render_template('notes/view.html',
                          title='View Note',
                          note=note)

@notes_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit a note"""
    note = Note.query.get_or_404(id)
    
    # Check if user can edit this note
    user_role = current_user.role
    can_edit = False
    
    if user_role in ['admin', 'product_owner', 'director']:
        can_edit = True
    elif note.created_by_id == current_user.id:
        can_edit = True
    elif user_role == 'manager' and note.user_id == current_user.id:
        can_edit = True
    
    if not can_edit:
        flash('You do not have permission to edit this note.', 'danger')
        return redirect(url_for('notes.index'))
    
    form = NoteForm(obj=note)
    
    # Set employee choices (same logic as create)
    if current_user.role == 'employee':
        form.employee_id.choices = [(current_user.id, current_user.get_full_name())]
        form.employee_id.data = current_user.id
    elif current_user.role == 'manager':
        try:
            department_employees = User.query.filter(
                User.status == 'active',
                User.department_id == current_user.department_id,
                ~User.first_name.like('User%'),
                ~User.first_name.like('NN-%'),
                User.first_name != '',
                User.last_name != ''
            )
            
            reporting_employees = User.query.filter(
                User.status == 'active',
                User.manager_id == current_user.id,
                ~User.first_name.like('User%'),
                ~User.first_name.like('NN-%'),
                User.first_name != '',
                User.last_name != ''
            )
            
            employees = department_employees.union(reporting_employees).order_by(User.first_name).all()
            
            employee_choices = [(current_user.id, current_user.get_full_name())]
            for employee in employees:
                dept_name = employee.department.department_name if employee.department else "No Department"
                display_text = f"{employee.get_full_name()} ({dept_name})"
                employee_choices.append((employee.id, display_text))
            
            form.employee_id.choices = employee_choices
        except Exception as e:
            current_app.logger.error(f"Error fetching employees for manager: {e}")
            form.employee_id.choices = [(current_user.id, current_user.get_full_name())]
    else:
        employees = User.query.filter(
            User.status == 'active',
            ~User.first_name.like('User%'),
            ~User.first_name.like('NN-%'),
            User.first_name != '',
            User.last_name != ''
        ).order_by(User.first_name).all()
        
        employee_choices = []
        for employee in employees:
            dept_name = employee.department.department_name if employee.department else "No Department"
            display_text = f"{employee.get_full_name()} ({dept_name})"
            employee_choices.append((employee.id, display_text))
        
        form.employee_id.choices = employee_choices
    
    # Set current employee
    form.employee_id.data = note.user_id
    
    if form.validate_on_submit():
        # Determine which employee the note is for
        if current_user.role == 'employee':
            employee_id = current_user.id
        else:
            employee_id = form.employee_id.data
        
        employee = User.query.get(employee_id)
        if not employee:
            flash('Selected employee does not exist.', 'danger')
            return redirect(url_for('notes.edit', id=note.id))
        
        # Store old values for logging
        old_start_date = note.start_date
        old_end_date = note.end_date
        old_comment = note.comment
        
        note.user_id = employee_id
        note.start_date = form.start_date.data
        note.end_date = form.end_date.data
        note.comment = form.comment.data
        note.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log note update
        date_range = f"{form.start_date.data.strftime('%Y-%m-%d')}"
        if form.start_date.data != form.end_date.data:
            date_range = f"{form.start_date.data.strftime('%Y-%m-%d')} to {form.end_date.data.strftime('%Y-%m-%d')}"
        
        log_activity(
            user=current_user,
            action='edit_note',
            entity_type='note',
            entity_id=note.id,
            before_values={
                'user_id': note.user_id,
                'date_range': f"{old_start_date.strftime('%Y-%m-%d')} to {old_end_date.strftime('%Y-%m-%d')}" if old_start_date != old_end_date else old_start_date.strftime('%Y-%m-%d'),
                'comment': old_comment[:100] if len(old_comment) > 100 else old_comment
            },
            after_values={
                'user_id': employee_id,
                'employee_name': employee.get_full_name(),
                'date_range': date_range,
                'comment': form.comment.data[:100] if len(form.comment.data) > 100 else form.comment.data
            },
            description=f'User {current_user.get_full_name()} edited note #{note.id} for {employee.get_full_name()}'
        )
        
        flash('Note updated successfully!', 'success')
        return redirect(url_for('notes.index'))
    
    return render_template('notes/edit.html',
                          title='Edit Note',
                          form=form,
                          note=note)

@notes_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    """Delete a note"""
    note = Note.query.get_or_404(id)
    
    # Check if user can delete this note
    user_role = current_user.role
    can_delete = False
    
    if user_role in ['admin', 'product_owner', 'director']:
        can_delete = True
    elif note.created_by_id == current_user.id:
        can_delete = True
    
    if not can_delete:
        flash('You do not have permission to delete this note.', 'danger')
        return redirect(url_for('notes.index'))
    
    employee_name = note.user.get_full_name() if note.user else 'Unknown'
    note_id = note.id
    
    db.session.delete(note)
    db.session.commit()
    
    # Log note deletion
    log_activity(
        user=current_user,
        action='delete_note',
        entity_type='note',
        entity_id=note_id,
        before_values={
            'user_id': note.user_id,
            'employee_name': employee_name,
            'date_range': f"{note.start_date.strftime('%Y-%m-%d')} to {note.end_date.strftime('%Y-%m-%d')}" if note.start_date != note.end_date else note.start_date.strftime('%Y-%m-%d'),
            'comment': note.comment[:100] if len(note.comment) > 100 else note.comment
        },
        after_values=None,
        description=f'User {current_user.get_full_name()} deleted note #{note_id} for {employee_name}'
    )
    
    flash('Note deleted successfully!', 'success')
    return redirect(url_for('notes.index'))
