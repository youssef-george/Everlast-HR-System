from flask import Blueprint, render_template, jsonify
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import LeaveRequest, PermissionRequest, User, Department
from helpers import role_required

calendar_bp = Blueprint('calendar', __name__, url_prefix='/calendar')

@calendar_bp.route('/')
@login_required
def index():
    from models import User
    all_users = User.query.order_by(User.first_name).all()
    """Show the calendar page"""
    return render_template('calendar/index.html', title='Calendar', all_users=all_users)

@calendar_bp.route('/events')
@login_required
def events():

    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.debug("Entering events() function.")
    logging.debug(f"Request args: {request.args}")
    logging.debug(f"Current user authenticated: {current_user.is_authenticated}")
    if current_user.is_authenticated:
        logging.debug(f"Current user ID: {current_user.id}, Role: {current_user.role}")
    filter_user_id = request.args.get('user_id', type=int)
    logging.debug(f"Current user role: {current_user.role}")
    logging.debug(f"Filter user ID: {filter_user_id}")
    """API endpoint to get calendar events based on user role"""
    user_role = current_user.role
    start_date = datetime.today() - timedelta(days=30)  # Default: show from 30 days ago
    end_date = datetime.today() + timedelta(days=90)    # Default: show 90 days ahead
    
    events = []
    
    if user_role == 'employee':
        # Employees see only their own leaves and permissions
        user_id = current_user.id
        if filter_user_id and filter_user_id != user_id:
            # Employees cannot view other users' data
            logging.debug("Employee trying to view other user's data. Returning empty.")
            return jsonify([])
    elif filter_user_id:
        # If a specific user is selected, override role-based filtering for managers/admins
        user_id = filter_user_id
        # Check if the current user is authorized to view this specific user's data
        if user_role == 'manager':
            from helpers import get_employees_for_manager
            managed_employees = get_employees_for_manager(current_user.id)
            if user_id not in [emp.id for emp in managed_employees] and user_id != current_user.id:
                logging.debug("Manager trying to view unauthorized user's data. Returning empty.")
                return jsonify([])
        elif user_role in ['admin', 'director']:
            # Admins/Directors can view any user's data, but we still set user_id for specific filtering
            pass
        else:
            # Other roles (if any) cannot view other users' data
            return jsonify([])
    else:
        # Default behavior based on role if no specific user is filtered
        user_id = current_user.id # This line is effectively redundant if filter_user_id is handled above, but kept for clarity

    logging.debug(f"Processing events for user_id: {user_id} with role: {user_role}")

    # Initialize leaves and permissions lists
    leaves = []
    permissions = []

    # Fetch initial leaves and permissions based on role/filter
    if user_role == 'employee' or (filter_user_id and user_id == current_user.id):
        # Employees (or current user if filtered) see only their own leaves and permissions
        leaves = LeaveRequest.query.filter_by(user_id=user_id).all()
        permissions = PermissionRequest.query.filter_by(user_id=user_id).all()
        logging.debug(f"Fetched {len(leaves)} leaves and {len(permissions)} permissions for employee/filtered user.")
        for leave in leaves:
            color = '#17a74a' if leave.status == 'approved' else '#dc3545' if leave.status == 'rejected' else '#ffc107'
            events.append({
                'id': f"leave_{leave.id}",
                'title': f"Leave: {leave.reason[:20]}{'...' if len(leave.reason) > 20 else ''}",
                'start': leave.start_date.isoformat(),
                'end': (leave.end_date + timedelta(days=1)).isoformat(),  # Add 1 day to make it inclusive
                'color': color,
                'url': f"/leave/view/{leave.id}",
                'status': leave.status,
                'type': 'leave'
            })



        for permission in permissions:
            color = '#17a74a' if permission.status == 'approved' else '#dc3545' if permission.status == 'rejected' else '#ffc107'
            events.append({
                'id': f"permission_{permission.id}",
                'title': f"Permission: {permission.reason[:20]}{'...' if len(permission.reason) > 20 else ''}",
                'start': permission.start_time.isoformat(),
                'end': permission.end_time.isoformat(),
                'color': color,
                'url': f"/permission/view/{permission.id}",
                'status': permission.status,
                'type': 'permission'
            })
        logging.debug(f"Added {len(permissions)} permission events.")

    # Re-fetch or refine leaves and permissions based on the determined user_id or role for managers/admins
    if filter_user_id:
        # If a specific user is selected, filter leaves and permissions for that user
        leaves = LeaveRequest.query.filter_by(user_id=user_id).all()
        permissions = PermissionRequest.query.filter_by(user_id=user_id).all()
        logging.debug(f"Re-fetched {len(leaves)} leaves and {len(permissions)} permissions for filtered user.")
    elif user_role == 'manager':
        # Managers see their own and their managed employees' leaves and permissions
        from helpers import get_employees_for_manager
        employees = get_employees_for_manager(current_user.id)
        employee_ids = [emp.id for emp in employees] + [current_user.id]
        leaves = LeaveRequest.query.filter(LeaveRequest.user_id.in_(employee_ids)).all()
        permissions = PermissionRequest.query.filter(PermissionRequest.user_id.in_(employee_ids)).all()
        logging.debug(f"Fetched {len(leaves)} leaves and {len(permissions)} permissions for manager and managed employees.")
    elif user_role in ['admin', 'director']:
        # Admins/Directors see all leaves and permissions
        leaves = LeaveRequest.query.all()
        permissions = PermissionRequest.query.all()
        logging.debug(f"Fetched {len(leaves)} leaves and {len(permissions)} permissions for admin/director.")
    else:
        # Default for employee role (already handled above, but as a fallback)
        leaves = LeaveRequest.query.filter_by(user_id=current_user.id).all()
        permissions = PermissionRequest.query.filter_by(user_id=current_user.id).all()
        logging.debug(f"Fetched {len(leaves)} leaves and {len(permissions)} permissions for employee fallback.")

    for leave in leaves:
        color = '#17a74a' if leave.status == 'approved' else '#dc3545' if leave.status == 'rejected' else '#ffc107'
        events.append({
            'id': f"leave_{leave.id}",
            'title': f"{leave.user.get_full_name()} - Leave",
            'start': leave.start_date.isoformat(),
            'end': (leave.end_date + timedelta(days=1)).isoformat(),
            'color': color,
            'url': f"/leave/view/{leave.id}",
            'status': leave.status,
            'type': 'leave'
        })

    for permission in permissions:
        color = '#17a74a' if permission.status == 'approved' else '#dc3545' if permission.status == 'rejected' else '#ffc107'
        events.append({
            'id': f"permission_{permission.id}",
            'title': f"{permission.user.get_full_name()} - Permission",
            'start': permission.start_time.isoformat(),
            'end': permission.end_time.isoformat(),
            'color': color,
            'url': f"/permission/view/{permission.id}",
            'status': permission.status,
            'type': 'permission'
        })


    # Fetch and add attendance data for all roles
    from models import DailyAttendance

    # Determine the scope of attendance data based on user role and filter_user_id
    attendance_query = DailyAttendance.query.filter(
        DailyAttendance.date.between(start_date, end_date)
    )

    if filter_user_id:
        attendance_query = attendance_query.filter_by(user_id=user_id)
    elif user_role == 'employee':
        attendance_query = attendance_query.filter_by(user_id=current_user.id)
    elif user_role == 'manager':
        from helpers import get_employees_for_manager
        employees = get_employees_for_manager(current_user.id)
        employee_ids = [emp.id for emp in employees] + [current_user.id]
        attendance_query = attendance_query.filter(DailyAttendance.user_id.in_(employee_ids))
    elif user_role in ['admin', 'director']:
        if current_user.managed_department:
            admin_dept_ids = [dept.id for dept in current_user.managed_department]
            attendance_query = attendance_query.join(User).filter(User.department_id.in_(admin_dept_ids))
        logging.debug(f"Attendance query for admin/director: {attendance_query}")

    attendance_records = attendance_query.all()

    for record in attendance_records:
        employee = User.query.get(record.user_id)
        title_prefix = "My " if record.user_id == current_user.id else f"{employee.get_full_name()} - "
        color = '#6c757d' # Default grey for attendance
        attendance_type = "Attendance"

        if record.status == 'present':
            color = '#28a745' # Green for present
            attendance_type = "Present"
        elif record.status == 'absent':
            color = '#dc3545' # Red for absent
            attendance_type = "Absent"
        elif record.status == 'leave':
            color = '#ffc107' # Yellow for on leave
            attendance_type = "On Leave"
        elif record.status == 'day_off':
            color = '#007bff' # Blue for day off
            attendance_type = "Day Off"

        events.append({
            'id': f"attendance_{record.id}",
            'title': f"{title_prefix}{attendance_type}",
            'start': record.date.isoformat(),
            'end': record.date.isoformat(), # Attendance is for a single day
            'color': color,
            'url': f"/attendance?start_date={record.date.isoformat()}&end_date={record.date.isoformat()}&employee_id={record.user_id}",
            'status': attendance_type,
            'type': 'attendance'
        })

    
    logging.debug(f"Events list before jsonify: {events}")
    try:
        return jsonify(events)
    except Exception as e:
        logging.error(f"Error serializing events to JSON: {e}")
        logging.error(f"Problematic events data: {events}")
        return jsonify({'error': 'Internal server error during event serialization'}), 500





@calendar_bp.route('/summary')
@login_required
def summary():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    user_id = request.args.get('user_id')

    if not start_date_str or not end_date_str:
        return jsonify({'error': 'Start date and end date are required'}), 400

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # If a specific user is selected, use that user_id, otherwise use current_user.id
    target_user_id = int(user_id) if user_id and user_id.isdigit() else current_user.id

    from models import DailyAttendance, LeaveRequest # Import DailyAttendance model

    present_days = 0
    absent_days = 0
    day_offs = 0
    leave_days = 0
    effective_days = 0
    extra_hours = 0.0

    # Fetch daily attendance records for the user within the date range
    attendance_records = DailyAttendance.query.filter(
        DailyAttendance.user_id == target_user_id,
        DailyAttendance.date >= start_date,
        DailyAttendance.date <= end_date
    ).all()

    # Fetch approved leave requests for the user within the date range
    approved_leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == target_user_id,
        LeaveRequest.status == 'approved',
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date
    ).all()

    # Create a set of leave dates for quick lookup
    leave_dates = set()
    for leave in approved_leaves:
        current_leave_date = leave.start_date
        while current_leave_date <= leave.end_date:
            leave_dates.add(current_leave_date)
            current_leave_date += timedelta(days=1)

    # Iterate through each day in the range to calculate summary
    current_day = start_date
    while current_day <= end_date:
        # Check if it's a weekend (Saturday or Sunday) - assuming these are day-offs
        if current_day.weekday() == 5 or current_day.weekday() == 6: # Saturday (5) or Sunday (6)
            day_offs += 1
        elif current_day in leave_dates:
            leave_days += 1
        else:
            # Check if there's an attendance record for this day
            record_found = False
            for record in attendance_records:
                if record.date == current_day:
                    present_days += 1
                    effective_days += record.total_working_hours / 8.0 # Assuming 8 hours is a full effective day
                    if record.total_working_hours > 8:
                        extra_hours += (record.total_working_hours - 8) # Calculate extra hours if total working hours exceed 8
                    record_found = True
                    break
            if not record_found:
                absent_days += 1
        current_day += timedelta(days=1)

    return jsonify({
        'present_days': present_days,
        'absent_days': absent_days,
        'day_offs': day_offs,
        'leave_days': leave_days,
        'effective_days': effective_days,
        'extra_hours': extra_hours
    })
