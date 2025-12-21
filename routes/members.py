from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from app import db
from models import User, Department
from helpers import role_required
import re

members_bp = Blueprint('members', __name__, url_prefix='/members')

@members_bp.route('/')
@login_required
def index():
    """Page showing all active and inactive members in the system"""
    # All users can see all active members, regardless of role
    # Get all active users, sorted by department name, then by last name and first name
    active_users = User.query.filter(
        User.status == 'active',
        ~User.first_name.like('User%'),  # Exclude generic test users
        ~User.first_name.like('NN-%'),   # Exclude numbered test users
        User.first_name != '',           # Exclude empty names
        User.last_name != ''             # Exclude users without last names
    ).all()

    # Sort users by department name, then by last name, then by first name
    def sort_users_by_department(user_list):
        # Define department order as requested
        custom_department_order = {
            'project management': 1,
            'human resources': 2,  # HR Department
            'hr department': 2,     # Alternative name
            'web development': 3,    # Web Dev Department
            'web dev department': 3, # Alternative name
            'information technology': 4,  # Information Technology
            'it department': 4,      # Alternative name
            'marketing': 5,          # Marketing
            'finance': 6,            # Finance
            'call center': 7,        # Call Center
            'business development': 8,  # Business Development
            'housekeeping': 9         # Housekeeping
        }
        
        def get_department_priority(user):
            """Get department priority for sorting"""
            if not user.department:
                return 999  # No department goes last
            dept_name = user.department.department_name.lower()
            # If department not in list, assign priority 8.5 (after call center, before housekeeping)
            return custom_department_order.get(dept_name, 8.5)
        
        def is_manager(user):
            """Check if user is a manager (has managed_department or role is manager)"""
            # Check if user has managed_department relationship (list)
            has_managed_dept = (hasattr(user, 'managed_department') and 
                               user.managed_department and 
                               len(user.managed_department) > 0)
            return user.role == 'manager' or has_managed_dept
        
        def is_youssef_george(user):
            """Check if user is Youssef George"""
            return (user.first_name and user.first_name.lower() == 'youssef' and
                   user.last_name and user.last_name.lower() == 'george')
        
        return sorted(user_list, key=lambda user: (
            # 1. Technical Support first (priority 0)
            0 if user.role == 'product_owner' else (
                # 2. Directors second (priority 1)
                1 if user.role == 'director' else 2
            ),
            # 3. Department order (technical support and directors already sorted, so this applies to others)
            get_department_priority(user) if user.role not in ['product_owner', 'director'] else 0,
            # 4. Manager first within department (0 = manager, 1 = employee)
            0 if is_manager(user) else 1,
            # 5. Youssef George after manager (0 = manager, 1 = Youssef George, 2 = other employees)
            1 if (not is_manager(user) and is_youssef_george(user)) else (
                0 if is_manager(user) else 2
            ),
            # 6. Alphabetical by Last Name, then First Name
            user.last_name.lower() if user.last_name else '',
            user.first_name.lower() if user.first_name else ''
        ))

    active_users = sort_users_by_department(active_users)
    # Get all departments for filtering
    departments = Department.query.all()
    
    return render_template('members/index.html', title='Company Members', active_users=active_users, departments=departments)

@members_bp.route('/search')
@login_required
def search():
    """AJAX endpoint for searching members"""
    search_query = request.args.get('q', '').strip()
    department_filter = request.args.get('department', 'all')
    status_filter = request.args.get('status', 'active')
    
    # Build query
    query = User.query
    
    if status_filter == 'active':
        query = query.filter_by(status='active')
    elif status_filter == 'inactive':
        query = query.filter_by(status='inactive')
    
    # Apply search filter
    if search_query:
        search_filter = f"%{search_query}%"
        query = query.filter(
            db.or_(
                User.first_name.ilike(search_filter),
                User.last_name.ilike(search_filter),
                User.email.ilike(search_filter),
                User.avaya_number.ilike(search_filter)
            )
        )
    
    # Apply department filter
    if department_filter != 'all':
        if department_filter == 'none':
            query = query.filter(User.department_id.is_(None))
        else:
            query = query.join(Department).filter(Department.department_name == department_filter)
    
    users = query.all()
    
    # Convert to JSON
    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'avaya_number': user.avaya_number or '',
            'role': user.role,
            'department': user.department.department_name if user.department else 'No Department',
            'profile_picture': user.profile_picture or '',
            'status': user.status
        })
    
    return jsonify({
        'users': users_data,
        'total': len(users_data)
    })

@members_bp.route('/<int:user_id>/details')
@login_required
def member_details(user_id):
    """Get employee details for popup view (API endpoint - kept for backward compatibility)"""
    user = User.query.get_or_404(user_id)
    
    # Check if current user is admin or technical support
    is_admin_or_owner = current_user.role in ['admin', 'product_owner']
    
    return jsonify({
        'id': user.id,
        'full_name': user.full_name or f"{user.first_name} {user.last_name}",
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'employee_code': user.employee_code or 'N/A',
        'insurance_number': user.insurance_number or 'N/A',
        'avaya_number': user.avaya_number or 'N/A',
        'fingerprint_number': user.fingerprint_number or 'N/A',
        'department': user.department.department_name if user.department else 'No Department',
        'role': user.role,
        'joining_date': user.joining_date.strftime('%Y-%m-%d') if user.joining_date else 'N/A',
        'phone_number': user.phone_number or 'N/A',
        'position': user.position or 'N/A',
        'viewer_role': current_user.role,
        'is_admin_or_owner': is_admin_or_owner
    })

@members_bp.route('/<slug>/profile')
@login_required
def member_profile(slug):
    """View individual employee profile page using slug (first-last-name format)"""
    # Parse the slug to extract first and last name
    # Slug format: firstname-lastname or firstname-lastname-1 (for duplicates)
    
    # Check if slug has a number suffix (for duplicate names)
    match = re.search(r'-(\d+)$', slug)
    suffix_num = None
    if match:
        suffix_num = int(match.group(1))
        # Remove the suffix to get base slug
        base_slug = slug[:match.start()]
    else:
        base_slug = slug
    
    # Split by hyphen to get name parts
    name_parts = base_slug.split('-')
    
    if len(name_parts) < 2:
        abort(404)
    
    # Reconstruct first and last name (handling multi-word names)
    # Assume last part is last name, everything else is first name
    first_name_parts = name_parts[:-1]
    last_name = name_parts[-1]
    first_name = ' '.join(first_name_parts)
    
    # Get all users with matching first and last name, ordered by ID
    matching_users = User.query.filter(
        db.func.lower(User.first_name) == first_name.lower(),
        db.func.lower(User.last_name) == last_name.lower()
    ).order_by(User.id).all()
    
    if not matching_users:
        abort(404)
    
    # If there's a suffix number, use that index (1-based)
    if suffix_num is not None:
        if suffix_num > 0 and len(matching_users) >= suffix_num:
            user = matching_users[suffix_num - 1]
        else:
            abort(404)
    else:
        # No suffix means it's the first user with this name
        user = matching_users[0]
    
    # Check if current user is admin or technical support
    is_admin_or_owner = current_user.role in ['admin', 'product_owner']
    
    return render_template('members/profile.html',
                         user=user,
                         is_admin_or_owner=is_admin_or_owner,
                         title=f"{user.get_full_name()} - Profile")

@members_bp.route('/<int:user_id>/update-fullname', methods=['POST'])
@login_required
@role_required(['admin', 'product_owner'])
def update_member_fullname(user_id):
    """Update full name from popup"""
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    if not data or 'full_name' not in data:
        return jsonify({'success': False, 'message': 'Full name is required'}), 400
    
    try:
        user.full_name = data['full_name'].strip() if data['full_name'].strip() else None
        db.session.commit()
        return jsonify({'success': True, 'message': 'Full name updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error updating full name: {str(e)}'}), 500


