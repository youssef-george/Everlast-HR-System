from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from models import db, User, LeaveRequest, PermissionRequest, DailyAttendance, Department, LeaveBalance, LeaveType, PaidHoliday, AttendanceLog
from helpers import role_required, get_dashboard_stats, get_employees_for_manager
from security import rate_limit, require_human
import logging
import hashlib
import hmac
import os

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/dashboard/stats')
@login_required
@rate_limit(max_requests=60, window=60)  # 60 requests per minute
def dashboard_stats():
    """API endpoint to get dashboard statistics for auto-fetch"""
    try:
        stats = get_dashboard_stats(current_user)
        return jsonify({
            'status': 'success',
            'data': stats
        })
    except Exception as e:
        logging.error(f"Error fetching dashboard stats: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch dashboard statistics'
        }), 500

@api_bp.route('/requests/recent')
@login_required
@rate_limit(max_requests=60, window=60)  # 60 requests per minute
def recent_requests():
    """API endpoint to get recent requests for auto-fetch"""
    try:
        user_role = current_user.role
        leave_requests = []
        permission_requests = []
        
        if user_role == 'employee':
            # Employee sees only their own requests
            leave_requests = LeaveRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
            
            permission_requests = PermissionRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
            
        elif user_role == 'manager':
            # Manager sees team requests
            employees = get_employees_for_manager(current_user.id)
            employee_ids = [emp.id for emp in employees]
            
            if employee_ids:
                leave_requests = LeaveRequest.query.filter(
                    LeaveRequest.user_id.in_(employee_ids),
                    LeaveRequest.status == 'pending',
                    LeaveRequest.manager_status == 'pending'
                ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
                
                permission_requests = PermissionRequest.query.filter(
                    PermissionRequest.user_id.in_(employee_ids),
                    PermissionRequest.status == 'pending',
                    PermissionRequest.admin_status == 'pending'
                ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
        
        elif user_role in ['admin', 'product_owner', 'director']:
            # Admin/Technical Support/Director sees all pending requests
            leave_requests = LeaveRequest.query.filter_by(
                status='pending'
            ).order_by(LeaveRequest.created_at.desc()).limit(5).all()
            
            permission_requests = PermissionRequest.query.filter_by(
                status='pending'
            ).order_by(PermissionRequest.created_at.desc()).limit(5).all()
        
        # Convert to JSON-serializable format
        leave_requests_data = []
        for lr in leave_requests:
            leave_requests_data.append({
                'id': lr.id,
                'title': f"{lr.user.first_name} {lr.user.last_name} - {lr.leave_type.name if lr.leave_type else 'Leave'}",
                'status': lr.status,
                'created_at': lr.created_at.isoformat(),
                'start_date': lr.start_date.isoformat(),
                'end_date': lr.end_date.isoformat(),
                'reason': lr.reason
            })
        
        permission_requests_data = []
        for pr in permission_requests:
            permission_requests_data.append({
                'id': pr.id,
                'title': f"{pr.user.first_name} {pr.user.last_name} - Permission",
                'status': pr.status,
                'created_at': pr.created_at.isoformat(),
                'start_time': pr.start_time.isoformat() if pr.start_time else None,
                'end_time': pr.end_time.isoformat() if pr.end_time else None,
                'reason': pr.reason
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'leave_requests': leave_requests_data,
                'permission_requests': permission_requests_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching recent requests: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch recent requests'
        }), 500

@api_bp.route('/team/data')
@login_required
@role_required(['manager', 'admin', 'product_owner', 'director'])
@rate_limit(max_requests=60, window=60)
def team_data():
    """API endpoint to get team data for managers"""
    try:
        employees = get_employees_for_manager(current_user.id)
        
        # Get team attendance for today
        today = date.today()
        team_attendance = DailyAttendance.query.filter(
            DailyAttendance.date == today,
            DailyAttendance.user_id.in_([emp.id for emp in employees]),
            DailyAttendance.status.in_(['present', 'half-day', 'in_office'])
        ).count()
        
        # Get team members data
        team_members_data = []
        for emp in employees:
            team_members_data.append({
                'id': emp.id,
                'name': f"{emp.first_name} {emp.last_name}",
                'role': emp.role,
                'status': emp.status,
                'department': emp.department.department_name if emp.department else 'No Department'
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'team_members': team_members_data,
                'team_attendance': team_attendance,
                'total_team_members': len(employees)
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching team data: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch team data'
        }), 500

@api_bp.route('/approvals/pending')
@login_required
@role_required(['manager', 'admin', 'product_owner', 'director'])
@rate_limit(max_requests=60, window=60)
def pending_approvals():
    """API endpoint to get pending approvals"""
    try:
        user_role = current_user.role
        pending_requests = []
        
        if user_role == 'manager':
            # Manager sees team requests that need their approval
            employees = get_employees_for_manager(current_user.id)
            employee_ids = [emp.id for emp in employees]
            
            if employee_ids:
                leave_requests = LeaveRequest.query.filter(
                    LeaveRequest.user_id.in_(employee_ids),
                    LeaveRequest.status == 'pending',
                    LeaveRequest.manager_status == 'pending'
                ).order_by(LeaveRequest.created_at.desc()).all()
                
                for lr in leave_requests:
                    pending_requests.append({
                        'id': lr.id,
                        'type': 'leave',
                        'title': f"{lr.user.first_name} {lr.user.last_name} - {lr.leave_type.name if lr.leave_type else 'Leave'}",
                        'status': lr.status,
                        'created_at': lr.created_at.isoformat(),
                        'start_date': lr.start_date.isoformat(),
                        'end_date': lr.end_date.isoformat(),
                        'reason': lr.reason
                    })
        
        elif user_role in ['admin', 'product_owner', 'director']:
            # Admin/Technical Support/Director sees all pending requests
            leave_requests = LeaveRequest.query.filter_by(
                status='pending'
            ).order_by(LeaveRequest.created_at.desc()).limit(10).all()
            
            permission_requests = PermissionRequest.query.filter_by(
                status='pending'
            ).order_by(PermissionRequest.created_at.desc()).limit(10).all()
            
            for lr in leave_requests:
                pending_requests.append({
                    'id': lr.id,
                    'type': 'leave',
                    'title': f"{lr.user.first_name} {lr.user.last_name} - {lr.leave_type.name if lr.leave_type else 'Leave'}",
                    'status': lr.status,
                    'created_at': lr.created_at.isoformat(),
                    'start_date': lr.start_date.isoformat(),
                    'end_date': lr.end_date.isoformat(),
                    'reason': lr.reason
                })
            
            for pr in permission_requests:
                pending_requests.append({
                    'id': pr.id,
                    'type': 'permission',
                    'title': f"{pr.user.first_name} {pr.user.last_name} - Permission",
                    'status': pr.status,
                    'created_at': pr.created_at.isoformat(),
                    'start_time': pr.start_time.isoformat() if pr.start_time else None,
                    'end_time': pr.end_time.isoformat() if pr.end_time else None,
                    'reason': pr.reason
                })
        
        return jsonify({
            'status': 'success',
            'data': {
                'requests': pending_requests,
                'count': len(pending_requests)
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching pending approvals: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch pending approvals'
        }), 500

@api_bp.route('/requests/all-pending')
@login_required
@role_required(['admin', 'product_owner', 'director'])
@rate_limit(max_requests=60, window=60)
def all_pending_requests():
    """API endpoint to get all pending requests for admin/director"""
    try:
        # Get all pending leave requests
        leave_requests = LeaveRequest.query.filter_by(
            status='pending'
        ).order_by(LeaveRequest.created_at.desc()).all()
        
        # Get all pending permission requests
        permission_requests = PermissionRequest.query.filter_by(
            status='pending'
        ).order_by(PermissionRequest.created_at.desc()).all()
        
        # Convert to JSON-serializable format
        leave_requests_data = []
        for lr in leave_requests:
            leave_requests_data.append({
                'id': lr.id,
                'title': f"{lr.user.first_name} {lr.user.last_name} - {lr.leave_type.name if lr.leave_type else 'Leave'}",
                'status': lr.status,
                'created_at': lr.created_at.isoformat(),
                'start_date': lr.start_date.isoformat(),
                'end_date': lr.end_date.isoformat(),
                'reason': lr.reason,
                'department': lr.user.department.department_name if lr.user.department else 'No Department'
            })
        
        permission_requests_data = []
        for pr in permission_requests:
            permission_requests_data.append({
                'id': pr.id,
                'title': f"{pr.user.first_name} {pr.user.last_name} - Permission",
                'status': pr.status,
                'created_at': pr.created_at.isoformat(),
                'start_time': pr.start_time.isoformat() if pr.start_time else None,
                'end_time': pr.end_time.isoformat() if pr.end_time else None,
                'reason': pr.reason,
                'department': pr.user.department.department_name if pr.user.department else 'No Department'
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'leave_requests': leave_requests_data,
                'permission_requests': permission_requests_data,
                'total_pending': len(leave_requests) + len(permission_requests)
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching all pending requests: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch all pending requests'
        }), 500

@api_bp.route('/analytics/departments')
@login_required
@role_required(['admin', 'product_owner', 'director'])
@rate_limit(max_requests=30, window=60)
def department_analytics():
    """API endpoint to get department analytics"""
    try:
        departments = Department.query.all()
        department_data = []
        
        for dept in departments:
            dept_employees = User.query.filter_by(department_id=dept.id).count()
            dept_leaves = LeaveRequest.query.join(
                User, LeaveRequest.user_id == User.id
            ).filter(
                User.department_id == dept.id,
                LeaveRequest.status == 'approved'
            ).count()
            dept_permissions = PermissionRequest.query.join(
                User, PermissionRequest.user_id == User.id
            ).filter(
                User.department_id == dept.id,
                PermissionRequest.status == 'approved'
            ).count()
            
            department_data.append({
                'id': dept.id,
                'name': dept.department_name,
                'employees': dept_employees,
                'leaves': dept_leaves,
                'permissions': dept_permissions
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'departments': department_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching department analytics: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch department analytics'
        }), 500

@api_bp.route('/users/management')
@login_required
@role_required(['admin', 'product_owner', 'director'])
@rate_limit(max_requests=30, window=60)
def user_management():
    """API endpoint to get user management data"""
    try:
        users = User.query.filter(
            User.status == 'active',
            ~User.first_name.like('User%'),  # Exclude generic test users
            ~User.first_name.like('NN-%'),   # Exclude numbered test users
            User.first_name != '',           # Exclude empty names
            User.last_name != ''             # Exclude users without last names
        ).all()
        users_data = []
        
        for user in users:
            users_data.append({
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'email': user.email,
                'role': user.role,
                'department': user.department.department_name if user.department else 'No Department',
                'status': user.status,
                'created_at': user.created_at.isoformat()
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'users': users_data,
                'total_users': len(users)
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching user management data: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch user management data'
        }), 500

@api_bp.route('/analytics/company')
@login_required
@role_required('director')
@rate_limit(max_requests=30, window=60)
def company_analytics():
    """API endpoint to get company-wide analytics for director"""
    try:
        # Get company-wide statistics
        total_employees = User.query.filter(User.status == 'active', User.role != 'director').count()
        total_departments = Department.query.count()
        
        # Get leave statistics
        total_leaves = LeaveRequest.query.count()
        approved_leaves = LeaveRequest.query.filter_by(status='approved').count()
        pending_leaves = LeaveRequest.query.filter_by(status='pending').count()
        rejected_leaves = LeaveRequest.query.filter_by(status='rejected').count()
        
        # Get permission statistics
        total_permissions = PermissionRequest.query.count()
        approved_permissions = PermissionRequest.query.filter_by(status='approved').count()
        pending_permissions = PermissionRequest.query.filter_by(status='pending').count()
        rejected_permissions = PermissionRequest.query.filter_by(status='rejected').count()
        
        # Get attendance statistics for today
        today = date.today()
        present_today = DailyAttendance.query.filter(
            DailyAttendance.date == today,
            DailyAttendance.status.in_(['present', 'half-day', 'in_office'])
        ).count()
        
        attendance_rate = (present_today / total_employees * 100) if total_employees > 0 else 0
        
        return jsonify({
            'status': 'success',
            'data': {
                'overview': {
                    'total_employees': total_employees,
                    'total_departments': total_departments,
                    'present_today': present_today,
                    'attendance_rate': round(attendance_rate, 1)
                },
                'leaves': {
                    'total': total_leaves,
                    'approved': approved_leaves,
                    'pending': pending_leaves,
                    'rejected': rejected_leaves
                },
                'permissions': {
                    'total': total_permissions,
                    'approved': approved_permissions,
                    'pending': pending_permissions,
                    'rejected': rejected_permissions
                }
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching company analytics: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch company analytics'
        }), 500

@api_bp.route('/requests/overview')
@login_required
@role_required('director')
@rate_limit(max_requests=30, window=60)
def requests_overview():
    """API endpoint to get all requests overview for director"""
    try:
        # Get all requests
        all_leave_requests = LeaveRequest.query.all()
        all_permission_requests = PermissionRequest.query.all()
        
        # Calculate summary statistics
        leave_summary = {
            'total': len(all_leave_requests),
            'pending': len([r for r in all_leave_requests if r.status == 'pending']),
            'approved': len([r for r in all_leave_requests if r.status == 'approved']),
            'rejected': len([r for r in all_leave_requests if r.status == 'rejected'])
        }
        
        permission_summary = {
            'total': len(all_permission_requests),
            'pending': len([r for r in all_permission_requests if r.status == 'pending']),
            'approved': len([r for r in all_permission_requests if r.status == 'approved']),
            'rejected': len([r for r in all_permission_requests if r.status == 'rejected'])
        }
        
        return jsonify({
            'status': 'success',
            'data': {
                'summary': {
                    'leave_requests': leave_summary,
                    'permission_requests': permission_summary,
                    'total_requests': leave_summary['total'] + permission_summary['total']
                }
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching requests overview: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch requests overview'
        }), 500

@api_bp.route('/leave/requests')
@login_required
@rate_limit(max_requests=60, window=60)
def leave_requests():
    """API endpoint to get leave requests"""
    try:
        user_role = current_user.role
        leave_requests = []
        
        if user_role == 'employee':
            # Employee sees only their own requests
            leave_requests = LeaveRequest.query.filter_by(
                user_id=current_user.id
            ).order_by(LeaveRequest.created_at.desc()).all()
            
        elif user_role == 'manager':
            # Manager sees team requests
            employees = get_employees_for_manager(current_user.id)
            employee_ids = [emp.id for emp in employees]
            
            if employee_ids:
                leave_requests = LeaveRequest.query.filter(
                    LeaveRequest.user_id.in_(employee_ids)
                ).order_by(LeaveRequest.created_at.desc()).all()
        
        elif user_role in ['admin', 'product_owner', 'director']:
            # Admin/Technical Support/Director sees all requests
            leave_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
        
        # Convert to JSON-serializable format
        requests_data = []
        for lr in leave_requests:
            requests_data.append({
                'id': lr.id,
                'user_name': f"{lr.user.first_name} {lr.user.last_name}",
                'leave_type': lr.leave_type.name if lr.leave_type else 'Leave',
                'status': lr.status,
                'start_date': lr.start_date.isoformat(),
                'end_date': lr.end_date.isoformat(),
                'reason': lr.reason,
                'created_at': lr.created_at.isoformat(),
                'manager_status': lr.manager_status,
                'admin_status': lr.admin_status
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'requests': requests_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching leave requests: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch leave requests'
        }), 500

@api_bp.route('/leave/types')
@login_required
def leave_types():
    """API endpoint to get leave types"""
    try:
        leave_types = LeaveType.query.filter_by(is_active=True).all()
        types_data = []
        
        for lt in leave_types:
            types_data.append({
                'id': lt.id,
                'name': lt.name,
                'description': lt.description,
                'color': lt.color,
                'requires_balance': lt.requires_balance,
                'is_active': lt.is_active
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'types': types_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching leave types: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch leave types'
        }), 500

@api_bp.route('/leave/balances')
@login_required
def leave_balances():
    """API endpoint to get leave balances"""
    try:
        user_role = current_user.role
        current_year = datetime.now().year
        
        if user_role in ['admin', 'product_owner', 'director']:
            # Admin/Technical Support/Director sees all balances
            balances = LeaveBalance.query.join(LeaveType).join(User).filter(
                LeaveBalance.year == current_year
            ).all()
        else:
            # Others see only their own balances
            balances = LeaveBalance.query.join(LeaveType).filter(
                LeaveBalance.user_id == current_user.id,
                LeaveBalance.year == current_year
            ).all()
        
        balances_data = []
        for balance in balances:
            balances_data.append({
                'id': balance.id,
                'user_name': f"{balance.user.first_name} {balance.user.last_name}",
                'leave_type': balance.leave_type.name,
                'total_days': balance.total_days,
                'used_days': balance.used_days,
                'remaining_days': balance.remaining_days,
                'year': balance.year
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'balances': balances_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching leave balances: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch leave balances'
        }), 500

@api_bp.route('/attendance/data')
@login_required
def attendance_data():
    """API endpoint to get attendance data"""
    try:
        user_role = current_user.role
        today = date.today()
        
        if user_role == 'employee':
            # Employee sees only their own attendance
            records = DailyAttendance.query.filter_by(
                user_id=current_user.id,
                date=today
            ).all()
        elif user_role == 'manager':
            # Manager sees team attendance
            employees = get_employees_for_manager(current_user.id)
            employee_ids = [emp.id for emp in employees]
            
            if employee_ids:
                records = DailyAttendance.query.filter(
                    DailyAttendance.user_id.in_(employee_ids),
                    DailyAttendance.date == today
                ).all()
            else:
                records = []
        else:
            # Admin/Technical Support/Director sees all attendance
            records = DailyAttendance.query.filter_by(date=today).all()
        
        records_data = []
        for record in records:
            records_data.append({
                'id': record.id,
                'user_name': f"{record.user.first_name} {record.user.last_name}",
                'date': record.date.isoformat(),
                'status': record.status,
                'first_check_in': record.first_check_in.isoformat() if record.first_check_in else None,
                'last_check_out': record.last_check_out.isoformat() if record.last_check_out else None,
                'total_working_hours': record.total_working_hours
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'records': records_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching attendance data: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch attendance data'
        }), 500

@api_bp.route('/attendance/stats')
@login_required
def attendance_stats():
    """API endpoint to get attendance statistics"""
    try:
        user_role = current_user.role
        today = date.today()
        
        if user_role == 'employee':
            # Employee sees only their own stats
            total_days = 1
            present_days = DailyAttendance.query.filter_by(
                user_id=current_user.id,
                date=today,
                status='present'
            ).count()
        elif user_role == 'manager':
            # Manager sees team stats
            employees = get_employees_for_manager(current_user.id)
            total_days = len(employees)
            present_days = DailyAttendance.query.filter(
                DailyAttendance.user_id.in_([emp.id for emp in employees]),
                DailyAttendance.date == today,
                DailyAttendance.status.in_(['present', 'half-day', 'in_office'])
            ).count()
        else:
            # Admin/Director sees all stats
            total_employees = User.query.filter(User.status == 'active', User.role != 'director').count()
            present_days = DailyAttendance.query.filter(
                DailyAttendance.date == today,
                DailyAttendance.status.in_(['present', 'half-day', 'in_office'])
            ).count()
            total_days = total_employees
        
        attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
        
        return jsonify({
            'status': 'success',
            'data': {
                'stats': {
                    'total_days': total_days,
                    'present_days': present_days,
                    'attendance_rate': round(attendance_rate, 1)
                }
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching attendance stats: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch attendance stats'
        }), 500

@api_bp.route('/calendar/upcoming')
@login_required
def upcoming_events():
    """API endpoint to get upcoming events"""
    try:
        # Get upcoming paid holidays
        upcoming_holidays = PaidHoliday.query.filter(
            PaidHoliday.start_date >= date.today()
        ).order_by(PaidHoliday.start_date.asc()).limit(5).all()
        
        # Get upcoming leave requests for current user
        upcoming_leaves = LeaveRequest.query.filter(
            LeaveRequest.user_id == current_user.id,
            LeaveRequest.status == 'approved',
            LeaveRequest.start_date >= date.today()
        ).order_by(LeaveRequest.start_date.asc()).limit(5).all()
        
        events_data = []
        
        # Add holidays
        for holiday in upcoming_holidays:
            events_data.append({
                'id': f"holiday_{holiday.id}",
                'title': holiday.description,
                'date': holiday.start_date.isoformat(),
                'type': 'holiday',
                'end_date': holiday.end_date.isoformat() if holiday.end_date else None
            })
        
        # Add leave requests
        for leave in upcoming_leaves:
            events_data.append({
                'id': f"leave_{leave.id}",
                'title': f"{leave.leave_type.name if leave.leave_type else 'Leave'} - {leave.user.first_name} {leave.user.last_name}",
                'date': leave.start_date.isoformat(),
                'type': 'leave',
                'end_date': leave.end_date.isoformat()
            })
        
        # Sort by date
        events_data.sort(key=lambda x: x['date'])
        
        return jsonify({
            'status': 'success',
            'data': {
                'events': events_data
            }
        })
        
    except Exception as e:
        logging.error(f"Error fetching upcoming events: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to fetch upcoming events'
        }), 500

def verify_sync_signature(payload, signature):
    """Verify HMAC signature for sync requests"""
    sync_secret = os.environ.get('SYNC_SECRET', 'your-sync-secret-key')
    expected_signature = hmac.new(
        sync_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)

@api_bp.route('/sync_logs', methods=['POST'])
def sync_attendance_logs():
    """
    Secure endpoint for local sync agent to upload attendance logs
    Expected payload:
    {
        "device_id": "device_001",
        "logs": [
            {
                "user_id": 123,
                "timestamp": "2024-01-15T09:30:00",
                "action": "check_in"
            }
        ]
    }
    """
    try:
        # Verify signature
        signature = request.headers.get('X-Sync-Signature')
        if not signature:
            return jsonify({
                'status': 'error',
                'message': 'Missing signature'
            }), 401
        
        payload = request.get_data()
        if not verify_sync_signature(payload, signature):
            logging.warning(f"Invalid sync signature from IP: {request.remote_addr}")
            return jsonify({
                'status': 'error',
                'message': 'Invalid signature'
            }), 401
        
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
        
        device_id = data.get('device_id')
        logs = data.get('logs', [])
        
        if not device_id or not logs:
            return jsonify({
                'status': 'error',
                'message': 'Missing device_id or logs'
            }), 400
        
        processed_logs = 0
        skipped_logs = 0
        errors = []
        
        for log_data in logs:
            try:
                user_id = log_data.get('user_id')
                timestamp_str = log_data.get('timestamp')
                action = log_data.get('action', 'check_in')
                
                if not user_id or not timestamp_str:
                    errors.append(f"Missing user_id or timestamp in log: {log_data}")
                    continue
                
                # Parse timestamp
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except ValueError:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                
                # Check if user exists
                user = User.query.get(user_id)
                if not user:
                    errors.append(f"User {user_id} not found")
                    continue
                
                # Check for duplicate log (same user, same timestamp, same action)
                existing_log = AttendanceLog.query.filter_by(
                    user_id=user_id,
                    timestamp=timestamp,
                    action=action
                ).first()
                
                if existing_log:
                    skipped_logs += 1
                    continue
                
                # Create new attendance log
                new_log = AttendanceLog(
                    user_id=user_id,
                    timestamp=timestamp,
                    action=action,
                    device_id=device_id,
                    created_at=datetime.utcnow()
                )
                
                db.session.add(new_log)
                processed_logs += 1
                
            except Exception as log_error:
                errors.append(f"Error processing log {log_data}: {str(log_error)}")
                continue
        
        # Commit all changes
        if processed_logs > 0:
            db.session.commit()
            logging.info(f"Sync successful: {processed_logs} logs processed from device {device_id}")
        
        return jsonify({
            'status': 'success',
            'message': f'Sync completed',
            'processed': processed_logs,
            'skipped': skipped_logs,
            'errors': len(errors),
            'error_details': errors[:10]  # Limit error details
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in sync_logs endpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Internal server error during sync'
        }), 500
