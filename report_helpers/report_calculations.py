"""
Unified report calculation utilities for all reports and exports.
This ensures all reports use identical calculation logic based on the Final Report web view.
"""

from datetime import datetime, timedelta, date
from models import DailyAttendance, LeaveRequest, PermissionRequest, AttendanceLog, PaidHoliday, db
from sqlalchemy import or_, and_, func
from collections import namedtuple
import logging

# Define a structure for summary metrics to ensure consistency
SummaryMetrics = namedtuple('SummaryMetrics', [
    'total_days',
    'total_working_days', 
    'present_days',
    'absent_days',
    'annual_leave_days',
    'unpaid_leave_days',
    'paid_leave_days',
    'permission_hours',
    'day_off_days',
    'incomplete_days',
    'attendance_percentage',
    'extra_time_hours'
])

UserReport = namedtuple('UserReport', [
    'user',
    'summary_metrics',
    'attendance_records',
    'leave_requests',
    'permission_requests'
])

def calculate_unified_report_data(user, start_date, end_date):
    """
    Calculate comprehensive report data for a single user using the EXACT same logic 
    as the Final Report web view. This ensures consistency across all reports and exports.
    """
    # Get attendance records for the user in the date range
    attendance_records = DailyAttendance.query.filter(
        DailyAttendance.user_id == user.id,
        DailyAttendance.date >= start_date,
        DailyAttendance.date <= end_date
    ).order_by(DailyAttendance.date.desc()).all()
    
    # Get leave requests for the user in the date range
    leave_requests = LeaveRequest.query.filter(
        LeaveRequest.user_id == user.id,
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
        LeaveRequest.status.in_(['approved', 'pending'])
    ).order_by(LeaveRequest.start_date.desc()).all()
    
    # Get permission requests for the user in the date range
    # Convert dates to datetime for comparison
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())
    
    permission_requests = PermissionRequest.query.filter(
        PermissionRequest.user_id == user.id,
        PermissionRequest.start_time <= end_datetime,
        PermissionRequest.end_time >= start_datetime,
        PermissionRequest.status.in_(['approved', 'pending'])
    ).order_by(PermissionRequest.start_time.desc()).all()
    
    # Calculate summary metrics using the EXACT same logic as the main final_report function
    total_days = (end_date - start_date).days + 1
    
    # Calculate present and absent days more accurately
    present_days = 0
    absent_days = 0
    
    # Count actual days from attendance records
    for record in attendance_records:
        # A day is considered present if there's ANY log (check-in OR check-out) or if status is explicitly present
        if record.first_check_in or record.last_check_out or record.status in ['present', 'half-day', 'partial']:
            present_days += 1
        # Note: absent_days will be calculated later based on missing days in the date range

        # Attach all logs for the day to each DailyAttendance record
        start_of_day = datetime.combine(record.date, datetime.min.time())
        end_of_day = datetime.combine(record.date, datetime.max.time())
        raw_logs = AttendanceLog.query.filter(
            AttendanceLog.user_id == user.id,
            AttendanceLog.timestamp.between(start_of_day, end_of_day)
        ).order_by(AttendanceLog.timestamp).all()
        record.all_logs = [
            {
                'id': log.id,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'scan_type': log.scan_type
            } for log in raw_logs
        ]

        # Process attendance records to dynamically add check-in/out and hours worked for display
        # Ensure these attributes are present for template rendering
        record.check_in = record.first_check_in
        record.check_out = record.last_check_out

        hours_worked = 0.0
        extra_time = 0.0

        if record.first_check_in and record.last_check_out:
            time_diff = record.last_check_out - record.first_check_in
            hours_worked = time_diff.total_seconds() / 3600
            extra_time = hours_worked - 9 # Assuming 9 hours is standard
        elif record.is_incomplete_day:
            # If it's an incomplete day (single log), assign 9 hours as per business rule
            hours_worked = 9.0
            extra_time = 0.0
        
        # Format hours_worked to HH:MM
        total_seconds = int(hours_worked * 3600)
        h, remainder = divmod(total_seconds, 3600)
        m, _ = divmod(remainder, 60)
        record.formatted_hours_worked = f"{h:02}:{m:02}" if (h > 0 or m > 0) else "-"
        record.hours_worked = hours_worked # Keep raw value for other calculations if needed
        record.extra_time = extra_time
    
    # Calculate different types of leave days from actual leave requests
    annual_leave_days = 0  # This will now include both annual and sick leave
    unpaid_leave_days = 0
    paid_leave_days = 0
    
    for leave_request in leave_requests:
        # Calculate days within the date range
        leave_start = max(leave_request.start_date, start_date)
        leave_end = min(leave_request.end_date, end_date)
        if leave_start <= leave_end:
            days_count = (leave_end - leave_start).days + 1
            
            # Categorize by leave type
            if leave_request.leave_type:
                leave_type_name = leave_request.leave_type.name.lower()
                if 'annual' in leave_type_name or 'vacation' in leave_type_name or 'sick' in leave_type_name or 'illness' in leave_type_name:
                    # Combine annual and sick leave into one column
                    annual_leave_days += days_count
                elif 'unpaid' in leave_type_name:
                    unpaid_leave_days += days_count
                elif 'paid' in leave_type_name or 'holiday' in leave_type_name:
                    paid_leave_days += days_count
                else:
                    # Default to annual leave if type is unclear
                    annual_leave_days += days_count
            else:
                # Default to annual leave if no type specified
                annual_leave_days += days_count
    
    # Add paid holidays to paid leave days - only count holidays within the date range
    paid_holidays = PaidHoliday.query.filter(
        PaidHoliday.start_date <= end_date,
        db.or_(
            PaidHoliday.end_date.is_(None),
            PaidHoliday.end_date >= start_date
        )
    ).all()
    
    for paid_holiday in paid_holidays:
        # Calculate the actual overlap with the date range
        holiday_start = max(paid_holiday.start_date, start_date)
        holiday_end = min(paid_holiday.end_date or paid_holiday.start_date, end_date)
        
        if holiday_start <= holiday_end:
            # Count each day of the holiday that falls within the date range
            current_holiday_date = holiday_start
            while current_holiday_date <= holiday_end:
                # Check if this holiday day falls on a working day (Monday-Friday)
                if current_holiday_date.weekday() < 5:  # Monday = 0, Sunday = 6
                    paid_leave_days += 1
                current_holiday_date += timedelta(days=1)
    
    # Calculate permission hours from actual permission requests
    permission_hours = 0.0
    for permission_request in permission_requests:
        # Calculate hours within the date range
        perm_start = max(permission_request.start_time, datetime.combine(start_date, datetime.min.time()))
        perm_end = min(permission_request.end_time, datetime.combine(end_date, datetime.max.time()))
        if perm_start <= perm_end:
            duration = (perm_end - perm_start).total_seconds() / 3600  # Convert to hours
            permission_hours += duration
    
    # Calculate extra time (hours) using EXACT same logic as main final_report function
    extra_time_hours = 0.0
    
    # Process each day in the date range using Calendar Attendance Report logic
    current_date = start_date
    today = date.today()
    
    # Initialize processed_logs outside the loop (same as Calendar Attendance Report)
    processed_logs = {}
    
    while current_date <= end_date:
        # Initialize variables for this day
        status = 'Absent'
        check_in = None
        check_out = None
        hours_worked = 0.0
        
        # Check if before joining date
        if user.joining_date and current_date < user.joining_date:
            status = 'Not Yet Joined'
        elif current_date > today:
            status = 'Future Date'
        else:
            # Check for paid holidays first (same as Calendar Attendance Report)
            paid_holiday = PaidHoliday.query.filter(
                or_(
                    and_(PaidHoliday.holiday_type == 'day', PaidHoliday.start_date == current_date),
                    and_(PaidHoliday.holiday_type == 'range', 
                         PaidHoliday.start_date <= current_date, 
                         PaidHoliday.end_date >= current_date)
                )
            ).first()
            
            if paid_holiday:
                # Check if user has attendance logs
                start_datetime = datetime.combine(current_date, datetime.min.time())
                end_datetime = datetime.combine(current_date, datetime.max.time())
                today_logs = AttendanceLog.query.filter(
                    AttendanceLog.user_id == user.id,
                    AttendanceLog.timestamp.between(start_datetime, end_datetime)
                ).order_by(AttendanceLog.timestamp).all()
                
                if today_logs:
                    status = f"Present - {paid_holiday.description}"
                else:
                    status = paid_holiday.description
            else:
                # Get attendance logs for this date
                start_datetime = datetime.combine(current_date, datetime.min.time())
                end_datetime = datetime.combine(current_date, datetime.max.time())
                
                today_logs = AttendanceLog.query.filter(
                    AttendanceLog.user_id == user.id,
                    AttendanceLog.timestamp.between(start_datetime, end_datetime)
                ).order_by(AttendanceLog.timestamp).all()
            
            # Process logs using same logic as Calendar Attendance Report
            # Clear processed_logs for each date
            processed_logs.clear()
            for log in today_logs:
                if log.user_id not in processed_logs:
                    processed_logs[log.user_id] = {
                        'user': log.user,
                        'check_in': None,
                        'check_out': None,
                        'duration': None,
                        'status': 'absent',
                        'all_logs': []
                    }
                
                # Add log to all_logs
                processed_logs[log.user_id]['all_logs'].append(log)
            
            # Use dynamic attendance processing for each user
            for user_id_key, data in processed_logs.items():
                from routes.attendance import determine_attendance_type_dynamic
                attendance_result = determine_attendance_type_dynamic(data['all_logs'])
                
                data['check_in'] = attendance_result['check_in']
                data['check_out'] = attendance_result['check_out']
                data['is_incomplete'] = attendance_result['is_incomplete']
                
                # Set status based on dynamic result
                if data['check_in'] and data['check_out']:
                        data['status'] = 'present'
                        duration = data['check_out'].timestamp - data['check_in'].timestamp
                        data['duration'] = duration
                elif data['check_in'] and not data['check_out']:
                    data['status'] = 'present'  # Incomplete day still counts as present
                    data['duration'] = None
                else:
                    data['status'] = 'absent'
            
            # Check for day off (Friday/Saturday) - EXACT same as Calendar Attendance Report
            if current_date.weekday() in [4, 5]:  # Friday (4) or Saturday (5)
                if user.id in processed_logs and processed_logs[user.id]['status'] == 'present':
                    status = 'Day Off / Present'
                    check_in = processed_logs[user.id]['check_in'].timestamp if processed_logs[user.id]['check_in'] else None
                    check_out = processed_logs[user.id]['check_out'].timestamp if processed_logs[user.id]['check_out'] else None
                    is_incomplete = processed_logs[user.id].get('is_incomplete', False)
                    
                    # Check for permission requests on day off
                    permission_request = PermissionRequest.query.filter(
                        PermissionRequest.user_id == user.id,
                        func.date(PermissionRequest.start_time) == current_date,
                        PermissionRequest.status == 'approved'
                    ).first()
                    
                    # Only calculate extra time for complete days (not incomplete) and no permission request
                    if check_in and check_out and not is_incomplete and not permission_request:
                        time_diff = check_out - check_in
                        hours_worked = time_diff.total_seconds() / 3600
                        # Calculate extra time: actual hours - required 9 hours
                        extra_time_hours += (hours_worked - 9)
                else:
                    status = 'Day Off'
            else:
                # Check for leave requests
                leave_request = LeaveRequest.query.filter(
                    LeaveRequest.user_id == user.id,
                    LeaveRequest.start_date <= current_date,
                    LeaveRequest.end_date >= current_date,
                    LeaveRequest.status == 'approved'
                ).first()
                
                # Check for permission requests
                permission_request = PermissionRequest.query.filter(
                    PermissionRequest.user_id == user.id,
                    func.date(PermissionRequest.start_time) == current_date,
                    PermissionRequest.status == 'approved'
                ).first()
                
                # Check if user has attendance logs
                has_attendance_logs = user.id in processed_logs
                
                if has_attendance_logs:
                    # User has attendance logs - prioritize showing attendance
                    user_data = processed_logs[user.id]
                    check_in = user_data['check_in'].timestamp if user_data['check_in'] else None
                    check_out = user_data['check_out'].timestamp if user_data['check_out'] else None
                    
                    if user_data['status'] == 'present':
                        # Calculate hours worked and extra time (only if no leave request and not incomplete)
                        is_incomplete = user_data.get('is_incomplete', False)
                        if check_in and check_out and not is_incomplete:
                            time_diff = check_out - check_in
                            hours_worked = time_diff.total_seconds() / 3600
                            # Calculate extra time only if no leave request and no permission request: actual hours - required 9 hours
                            if not leave_request and not permission_request:
                                extra_time_hours += (hours_worked - 9)
                    elif user_data['status'] == 'in_office':
                        # Calculate hours worked and extra time for in_office status (only if no leave request and not incomplete)
                        is_incomplete = user_data.get('is_incomplete', False)
                        if check_in and check_out and not is_incomplete:
                            time_diff = check_out - check_in
                            hours_worked = time_diff.total_seconds() / 3600
                            # Calculate extra time only if no leave request and no permission request: actual hours - required 9 hours
                            if not leave_request and not permission_request:
                                extra_time_hours += (hours_worked - 9)
                    else:
                        # Calculate hours worked and extra time for other statuses (only if no leave request and not incomplete)
                        is_incomplete = user_data.get('is_incomplete', False)
                        if check_in and check_out and not is_incomplete:
                            time_diff = check_out - check_in
                            hours_worked = time_diff.total_seconds() / 3600
                            # Calculate extra time only if no leave request and no permission request: actual hours - required 9 hours
                            if not leave_request and not permission_request:
                                extra_time_hours += (hours_worked - 9)
                else:
                    # User has no attendance logs - check for leave/permission/paid holiday
                    if not leave_request and not permission_request and not paid_holiday:
                        # Only count as absent if it's not a future date
                        if current_date <= today:
                            status = 'Absent'
                            # Don't calculate negative working hours for absent days
        
        current_date += timedelta(days=1)
    
    # Calculate working days (Monday to Thursday) and Friday+Saturday days
    working_days = 0
    total_friday_saturday_days = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 4:  # Monday = 0, Tuesday = 1, Wednesday = 2, Thursday = 3
            working_days += 1
        elif current_date.weekday() in [4, 5]:  # Friday = 4, Saturday = 5
            total_friday_saturday_days += 1
        # Sunday = 6 is not counted in either
        current_date += timedelta(days=1)
    
    # Calculate actual day off days: total Friday+Saturday minus days worked/taken as leave
    # Count present days, annual leave, and paid leave that fall on Friday/Saturday
    friday_saturday_used_days = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() in [4, 5]:  # Friday = 4, Saturday = 5
            # Check if this Friday/Saturday was used for work or leave
            daily_record = None
            if attendance_records:
                daily_record = next((r for r in attendance_records if r.date == current_date), None)
            
            # Check for leave requests on this date
            leave_on_date = any(
                lr.start_date <= current_date <= lr.end_date and lr.status == 'approved'
                for lr in leave_requests
            )
            
            # Check for paid holidays on this date
            paid_holiday_on_date = any(
                (ph.holiday_type == 'day' and ph.start_date == current_date) or
                (ph.holiday_type == 'range' and ph.start_date <= current_date <= ph.end_date)
                for ph in paid_holidays
            )
            
            # If there's attendance, leave, or paid holiday on this Friday/Saturday, count it as used
            if (daily_record and daily_record.status == 'present') or leave_on_date or paid_holiday_on_date:
                friday_saturday_used_days += 1
        
        current_date += timedelta(days=1)
    
    # Day off days = Total Friday+Saturday days - Used Friday+Saturday days
    day_off_days = total_friday_saturday_days - friday_saturday_used_days
    day_off_days = max(0, day_off_days)  # Ensure it's not negative
    
    # Calculate absent days properly: count each working day in the range
    absent_days = 0
    current_date = start_date
    today = date.today()
    
    while current_date <= end_date:
        # Only count working days (Monday to Thursday) - exclude weekends
        if current_date.weekday() < 4:  # Monday = 0, Thursday = 3
            # Only count if date is on or after joining date and not in the future
            if (not user.joining_date or current_date >= user.joining_date) and current_date <= today:
                # Check if there's any record for this date
                has_attendance = any(record.date == current_date for record in attendance_records)
                
                # Check for leave requests on this date
                has_leave = any(
                    lr.start_date <= current_date <= lr.end_date and lr.status == 'approved'
                    for lr in leave_requests
                )
                
                # Check for paid holidays on this date
                has_paid_holiday = any(
                    (ph.holiday_type == 'day' and ph.start_date == current_date) or
                    (ph.holiday_type == 'range' and ph.start_date <= current_date <= ph.end_date)
                    for ph in paid_holidays
                )
                
                # Check for permission requests on this date
                has_permission = any(
                    pr.start_time.date() <= current_date <= pr.end_time.date() and pr.status == 'approved'
                    for pr in permission_requests
                )
                
                # Count as absent only if no attendance, leave, holiday, or permission
                if not has_attendance and not has_leave and not has_paid_holiday and not has_permission:
                    absent_days += 1
        
        current_date += timedelta(days=1)
    
    # Calculate incomplete days based on FIXED business rules:
    # - ONLY 1 log entry total: Mark as incomplete
    # - Multiple log entries (even with same timestamp): Complete day
    # - No logs: Absent (not incomplete)
    # FIXED: Days with 10+ logs are now correctly marked as complete
    incomplete_days = 0
    if attendance_records:
        incomplete_days = sum(1 for record in attendance_records if record.is_incomplete_day)
    
    # Calculate total working days as: day off + present + annual + paid
    total_working_days = day_off_days + present_days + annual_leave_days + paid_leave_days
    
    # Calculate attendance percentage based on total working days
    attendance_percentage = (present_days / total_working_days * 100) if total_working_days > 0 else 0
    
    summary_metrics = SummaryMetrics(
        total_days=total_days,
        total_working_days=total_working_days,  # Day Off + Present + Annual + Paid
        present_days=present_days,
        absent_days=absent_days,
        annual_leave_days=annual_leave_days,  # Now includes both annual and sick leave
        unpaid_leave_days=unpaid_leave_days,
        paid_leave_days=paid_leave_days,
        permission_hours=round(permission_hours, 2),
        day_off_days=day_off_days,
        incomplete_days=incomplete_days,  # Days with only one log
        attendance_percentage=round(attendance_percentage, 1),
        extra_time_hours=round(extra_time_hours, 1)
    )
    
    return UserReport(
        user=user,
        summary_metrics=summary_metrics,
        attendance_records=attendance_records,
        leave_requests=leave_requests,
        permission_requests=permission_requests
    )

def calculate_multiple_users_report_data(users, start_date, end_date):
    """
    Calculate report data for multiple users efficiently using unified logic.
    Returns a list of UserReport objects.
    """
    all_user_reports = []
    
    for user in users:
        user_report = calculate_unified_report_data(user, start_date, end_date)
        all_user_reports.append(user_report)
    
    return all_user_reports

# Legacy function names for backward compatibility
def calculate_user_report_data(user, start_date, end_date):
    """
    Legacy function name - now uses unified calculation logic.
    Maintained for backward compatibility.
    """
    return calculate_unified_report_data(user, start_date, end_date)