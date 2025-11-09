from flask_login import UserMixin
from datetime import datetime
from extensions import db
from sqlalchemy import Index

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    fingerprint_number = db.Column(db.String(50), nullable=True, unique=True)
    avaya_number = db.Column(db.String(50), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='employee')  # employee, manager, admin, product_owner, director
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    profile_picture = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, inactive
    joining_date = db.Column(db.Date, nullable=True)
    
    # Additional data fields (admin only)
    date_of_birth = db.Column(db.Date, nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    alternate_phone_number = db.Column(db.String(20), nullable=True)
    position = db.Column(db.String(100), nullable=True)  # Job position/title
    salary = db.Column(db.Float, nullable=True)  # Monthly salary
    currency = db.Column(db.String(10), nullable=True, default='USD')  # Currency code
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    department = db.relationship('Department', foreign_keys=[department_id], backref='employees')
    leave_requests = db.relationship('LeaveRequest', lazy=True, foreign_keys='LeaveRequest.user_id', primaryjoin="User.id == remote(LeaveRequest.user_id)")
    permission_requests = db.relationship('PermissionRequest', backref='user', lazy=True, foreign_keys='PermissionRequest.user_id')
    fingerprint_failures = db.relationship('FingerPrintFailure',
        primaryjoin="User.fingerprint_number==foreign(FingerPrintFailure.employee_id)",
        backref='user',
        lazy='dynamic'
    )
    delegate_leave_requests = db.relationship('LeaveRequest', lazy=True, foreign_keys='LeaveRequest.delegate_employee_id', primaryjoin="User.id == remote(LeaveRequest.delegate_employee_id)")
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_product_owner(self):
        return self.role == 'product_owner'
    
    def is_manager(self):
        return self.role == 'manager'
    
    def is_director(self):
        return self.role == 'director'
    
    def is_employee(self):
        return self.role == 'employee'
    
    def can_submit_for_others(self):
        """Check if user can submit leave/permission requests for other employees"""
        return self.role in ['admin', 'product_owner', 'manager']
    
    def can_auto_approve(self):
        """Check if user's submissions are auto-approved"""
        return self.role in ['admin', 'product_owner', 'manager']
    
    def get_manageable_employees(self):
        """Get list of employees this user can manage (submit requests for)"""
        if self.role in ['admin', 'product_owner']:
            # Admin and product owners can manage all active employees
            return User.query.filter(
                User.status == 'active',
                User.id != self.id
            ).all()
        elif self.role == 'manager':
            # Managers can only manage their team members
            from helpers import get_employees_for_manager
            return get_employees_for_manager(self.id)
        else:
            # Regular employees can't manage others
            return []
    
    def is_active(self):
        return self.status == 'active'
    
    
    # Indexes for better query performance
    __table_args__ = (
        Index('idx_user_role', 'role'),
        Index('idx_user_status', 'status'),
        Index('idx_user_department', 'department_id'),
        Index('idx_user_fingerprint', 'fingerprint_number'),
    )
    
    def __repr__(self):
        return f"<User {self.email}>"

    def get_daily_attendance(self, start_date=None, end_date=None):
        """Get daily attendance records for the user within a date range"""
        query = DailyAttendance.query.filter_by(user_id=self.id)
        
        if start_date:
            query = query.filter(DailyAttendance.date >= start_date)
        if end_date:
            query = query.filter(DailyAttendance.date <= end_date)
            
        return query.order_by(DailyAttendance.date.desc()).all()
    
    def get_monthly_working_hours(self, year, month):
        """Get total working hours for a specific month"""
        from sqlalchemy import func
        return db.session.query(func.sum(DailyAttendance.total_working_hours))\
            .filter(
                DailyAttendance.user_id == self.id,
                func.extract('year', DailyAttendance.date) == year,
                func.extract('month', DailyAttendance.date) == month
            ).scalar() or 0.0
    
    def get_attendance_stats(self, year, month):
        """Get attendance statistics for a specific month"""
        from sqlalchemy import func
        from datetime import date, timedelta
        import calendar
        
        # Get all daily attendance records for the month
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        
        records = DailyAttendance.query.filter(
            DailyAttendance.user_id == self.id,
            DailyAttendance.date >= month_start,
            DailyAttendance.date <= month_end
        ).all()
        
        # Calculate statistics
        total_days = (month_end - month_start).days + 1
        present_days = sum(1 for record in records if record.status == 'present')
        absent_days = sum(1 for record in records if record.status == 'absent')
        days_off = sum(1 for record in records if record.status in ['day_off', 'DayOff'] or record.is_day_off)
        half_days = sum(1 for record in records if record.status == 'half-day')
        leave_days = sum(1 for record in records if record.status == 'leave')
        
        # Calculate days without any record (weekends or holidays)
        recorded_dates = {record.date for record in records}
        days_without_record = 0
        current_date = month_start
        while current_date <= month_end:
            if current_date not in recorded_dates:
                # Check if it's a weekend (Saturday=5, Sunday=6)
                if current_date.weekday() >= 5:
                    days_off += 1
                else:
                    absent_days += 1
                days_without_record += 1
            current_date += timedelta(days=1)
        
        return {
            'total_days': total_days,
            'present_days': present_days,
            'absent_days': absent_days,
            'days_off': days_off,
            'half_days': half_days,
            'leave_days': leave_days,
            'days_without_record': days_without_record
        }

class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    department_name = db.Column(db.String(100), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    manager = db.relationship('User', foreign_keys=[manager_id], backref='managed_department')
    
    def __repr__(self):
        return f"<Department {self.department_name}>"

class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id', ondelete='CASCADE'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    reason = db.Column(db.Text, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    delegate_employee_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], primaryjoin="LeaveRequest.user_id == User.id", backref='leave_requests_as_requester')
    leave_type = db.relationship('LeaveType', backref='leave_requests')
    delegate_employee = db.relationship('User', foreign_keys=[delegate_employee_id], primaryjoin="LeaveRequest.delegate_employee_id == User.id", backref='leave_requests_as_delegate')
    
    # Updated approval fields
    manager_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    manager_comment = db.Column(db.Text, nullable=True)
    manager_updated_at = db.Column(db.DateTime, nullable=True)
    
    admin_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_comment = db.Column(db.Text, nullable=True)
    admin_updated_at = db.Column(db.DateTime, nullable=True)
    
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delegate_employee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    def can_edit(self):
        return self.status == 'pending'
    
    def update_overall_status(self):
        """Update the overall status based on manager and admin approval only"""
        if self.manager_status == 'rejected' or self.admin_status == 'rejected':
            self.status = 'rejected'
        elif self.manager_status == 'approved' and self.admin_status == 'approved':
            self.status = 'approved'
        else:
            self.status = 'pending'
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('leave_requests_as_requester', lazy='dynamic'))
    delegate_employee = db.relationship('User', foreign_keys=[delegate_employee_id], backref=db.backref('delegated_leave_requests', lazy='dynamic'))
    leave_type = db.relationship('LeaveType', backref='leave_requests')
    
    # Indexes for better query performance
    __table_args__ = (
        Index('idx_leave_user_created', 'user_id', 'created_at'),
        Index('idx_leave_status', 'status'),
        Index('idx_leave_manager_status', 'manager_status'),
        Index('idx_leave_admin_status', 'admin_status'),
        Index('idx_leave_dates', 'start_date', 'end_date'),
    )
    
    def __repr__(self):
        return f"<LeaveRequest {self.id} - {self.status}>"

class PermissionRequest(db.Model):
    __tablename__ = 'permission_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    reason = db.Column(db.Text, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    
    # Approval fields - only admin approval required
    admin_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_comment = db.Column(db.Text, nullable=True)
    admin_updated_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def can_edit(self):
        return self.status == 'pending'
    
    def update_overall_status(self):
        """Update the overall status based on admin approval only"""
        if self.admin_status == 'rejected':
            self.status = 'rejected'
        elif self.admin_status == 'approved':
            self.status = 'approved'
        else:
            self.status = 'pending'
    
    def __repr__(self):
        return f"<PermissionRequest {self.id} - {self.status}>"


class SMTPConfiguration(db.Model):
    __tablename__ = 'smtp_configurations'
    
    id = db.Column(db.Integer, primary_key=True)
    smtp_server = db.Column(db.String(255), nullable=False)
    smtp_port = db.Column(db.Integer, nullable=False, default=587)
    smtp_username = db.Column(db.String(255), nullable=False)
    smtp_password = db.Column(db.Text, nullable=False)  # This should be encrypted in production
    use_tls = db.Column(db.Boolean, default=True)
    use_ssl = db.Column(db.Boolean, default=False)
    sender_name = db.Column(db.String(255), nullable=False, default='EverLastERP System')
    sender_email = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Module-specific email lists (comma-separated email addresses)
    leave_notification_emails = db.Column(db.Text, nullable=True, default='')  # Emails for leave requests
    permission_notification_emails = db.Column(db.Text, nullable=True, default='')  # Emails for permission requests
    admin_notification_emails = db.Column(db.Text, nullable=True, default='')  # General admin notifications
    
    # Notification settings
    notify_leave_requests = db.Column(db.Boolean, default=True)  # Enable/disable leave notifications
    notify_permission_requests = db.Column(db.Boolean, default=True)  # Enable/disable permission notifications
    notify_admin_only = db.Column(db.Boolean, default=False)  # Send only to admin emails, not all admin users
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_leave_emails(self):
        """Get list of emails for leave notifications"""
        if self.notify_admin_only and self.leave_notification_emails:
            return [email.strip() for email in self.leave_notification_emails.split(',') if email.strip()]
        elif not self.notify_admin_only:
            # Return all admin and product owner user emails
            admin_emails = [user.email for user in User.query.filter(User.role.in_(['admin', 'product_owner']), User.status == 'active').all()]
            if self.leave_notification_emails:
                custom_emails = [email.strip() for email in self.leave_notification_emails.split(',') if email.strip()]
                admin_emails.extend(custom_emails)
            return list(set(admin_emails))  # Remove duplicates
        return []
    
    def get_permission_emails(self):
        """Get list of emails for permission notifications"""
        if self.notify_admin_only and self.permission_notification_emails:
            return [email.strip() for email in self.permission_notification_emails.split(',') if email.strip()]
        elif not self.notify_admin_only:
            # Return all admin and product owner user emails
            admin_emails = [user.email for user in User.query.filter(User.role.in_(['admin', 'product_owner']), User.status == 'active').all()]
            if self.permission_notification_emails:
                custom_emails = [email.strip() for email in self.permission_notification_emails.split(',') if email.strip()]
                admin_emails.extend(custom_emails)
            return list(set(admin_emails))  # Remove duplicates
        return []
    
    def get_admin_emails(self):
        """Get list of emails for general admin notifications"""
        if self.admin_notification_emails:
            return [email.strip() for email in self.admin_notification_emails.split(',') if email.strip()]
        return [user.email for user in User.query.filter(User.role.in_(['admin', 'product_owner']), User.status == 'active').all()]
    
    def __repr__(self):
        return f"<SMTPConfiguration {self.id} - {self.smtp_server}:{self.smtp_port}>"

class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device_settings.id', ondelete='SET NULL'), nullable=True)  # Reference to device
    device_ip = db.Column(db.String(15), nullable=False)  # Store the fingerprint device IP (legacy field)
    scan_type = db.Column(db.String(10), nullable=False)  # check-in, check-out
    duration = db.Column(db.Integer, nullable=True)  # Duration in minutes since last check-in
    pair_id = db.Column(db.Integer, nullable=True)  # ID of the matching check-in/out record
    scan_order = db.Column(db.Integer, nullable=True) # Order of scan for the day (1st, 2nd, 3rd, etc.)
    is_extra_scan = db.Column(db.Boolean, default=False) # True if it's a 3rd or subsequent scan for the day
    raw_scan_id = db.Column(db.Integer, nullable=True) # Optional: Link to raw scan if stored separately
    check_in_id = db.Column(db.Integer, db.ForeignKey('attendance_logs.id'), nullable=True)
    check_out_id = db.Column(db.Integer, db.ForeignKey('attendance_logs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('attendance_logs', lazy=True, order_by='AttendanceLog.timestamp.desc()'))
    
    # Indexes for better query performance
    __table_args__ = (
        Index('idx_attendance_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_attendance_timestamp', 'timestamp'),
        Index('idx_attendance_scan_type', 'scan_type'),
        Index('idx_attendance_user_date', 'user_id', db.text('DATE(timestamp)')),
        Index('idx_attendance_device', 'device_id'),
        Index('idx_attendance_device_ip', 'device_ip'),
    )
    
    def __repr__(self):
        return f"<AttendanceLog {self.id} - User {self.user_id} - {self.scan_type}>"
    
    def format_duration(self):
        """Format duration in minutes to readable string"""
        if not self.duration:
            return "-"
        hours = self.duration // 60
        minutes = self.duration % 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

class DailyAttendance(db.Model):
    __tablename__ = 'daily_attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    first_check_in = db.Column(db.DateTime, nullable=True)
    last_check_out = db.Column(db.DateTime, nullable=True)
    total_working_hours = db.Column(db.Float, nullable=True)  # Store hours as decimal
    total_breaks = db.Column(db.Integer, nullable=True)  # Total break time in minutes
    entry_count = db.Column(db.Integer, default=0)  # Number of check-in/out pairs
    status = db.Column(db.String(20), default='present')  # present, absent, half-day, leave, permission, day_off, paid_holiday
    is_day_off = db.Column(db.Boolean, default=False)  # Flag to explicitly mark day off status
    is_late = db.Column(db.Boolean, default=False)  # Flag to mark if employee was late
    is_incomplete_day = db.Column(db.Boolean, default=False)  # Flag for days with only 1 log
    status_reason = db.Column(db.String(100), nullable=True)  # Additional status context
    
    # New fields for leave and holiday tracking
    leave_request_id = db.Column(db.Integer, db.ForeignKey('leave_requests.id', ondelete='SET NULL'), nullable=True)
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id', ondelete='SET NULL'), nullable=True)
    paid_holiday_id = db.Column(db.Integer, db.ForeignKey('paid_holidays.id', ondelete='SET NULL'), nullable=True)
    is_paid_holiday = db.Column(db.Boolean, default=False)  # Flag for company-wide paid holidays
    leave_type_name = db.Column(db.String(100), nullable=True)  # Cached leave type name for display
    holiday_name = db.Column(db.String(255), nullable=True)  # Cached holiday name for display
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('daily_attendance', lazy=True))
    leave_request = db.relationship('LeaveRequest', backref=db.backref('daily_attendance', lazy=True))
    leave_type = db.relationship('LeaveType', backref=db.backref('daily_attendance', lazy=True))
    paid_holiday = db.relationship('PaidHoliday', backref=db.backref('daily_attendance', lazy=True))
    
    def __repr__(self):
        return f"<DailyAttendance {self.date} - User {self.user_id}>"
    
    def format_working_hours(self):
        """Format working hours to readable string"""
        if not self.total_working_hours:
            return "-"
        hours = int(self.total_working_hours)
        minutes = int((self.total_working_hours - hours) * 60)
        return f"{hours}h {minutes}m"
    
    def format_breaks(self):
        """Format break time to readable string"""
        if not self.total_breaks:
            return "-"
        hours = self.total_breaks // 60
        minutes = self.total_breaks % 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

class FingerPrintFailure(db.Model):
    """Model for tracking failed fingerprint attempts"""
    __tablename__ = 'fingerprint_failures'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    device_ip = db.Column(db.String(15), nullable=False)
    error_type = db.Column(db.String(50), nullable=False)  # 'unread', 'no_match', 'device_error'
    error_message = db.Column(db.Text)
    raw_device_data = db.Column(db.Text)  # Store any raw data from device
    employee_id = db.Column(db.String(50))  # Optional - if device provides an attempted ID
    resolved = db.Column(db.Boolean, default=False)
    resolution_note = db.Column(db.Text)
    manual_entry = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<FingerPrintFailure {self.timestamp} - {self.error_type}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'device_ip': self.device_ip,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'employee_id': self.employee_id,
            'resolved': self.resolved,
            'manual_entry': self.manual_entry
        }

class DeviceSettings(db.Model):
    """Model for storing fingerprint device settings - Enhanced for multiple devices"""
    __tablename__ = 'device_settings'

    id = db.Column(db.Integer, primary_key=True)
    device_ip = db.Column(db.String(15), nullable=False, default='192.168.11.2')
    device_port = db.Column(db.Integer, nullable=False, default=4370)
    device_name = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    attendance_logs = db.relationship('AttendanceLog', backref='device', lazy=True)
    device_users = db.relationship('DeviceUser', backref='device', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DeviceSettings {self.device_name or "Unnamed"} ({self.device_ip}:{self.device_port})>'

    def get_display_name(self):
        """Get display name for the device"""
        return self.device_name or f"Device {self.id} ({self.device_ip})"

class DeviceUser(db.Model):
    """Model for storing users found on devices that haven't been added to the system yet"""
    __tablename__ = 'device_users'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device_settings.id', ondelete='CASCADE'), nullable=False)
    device_user_id = db.Column(db.String(50), nullable=False)  # User ID on the device
    device_uid = db.Column(db.String(50), nullable=True)  # UID on the device
    device_name = db.Column(db.String(100), nullable=True)  # Name on the device
    privilege = db.Column(db.String(20), nullable=True)  # User privilege on device
    group_id = db.Column(db.String(50), nullable=True)  # Group ID on device
    card = db.Column(db.String(50), nullable=True)  # Card number if any
    is_processed = db.Column(db.Boolean, default=False)  # Whether this user has been processed
    system_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)  # Link to system user if created
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    system_user = db.relationship('User', backref='device_user_records')

    # Indexes for better query performance
    __table_args__ = (
        Index('idx_device_user_device_id', 'device_id'),
        Index('idx_device_user_device_user_id', 'device_user_id'),
        Index('idx_device_user_processed', 'is_processed'),
        Index('idx_device_user_system_user', 'system_user_id'),
    )

    def __repr__(self):
        return f'<DeviceUser {self.device_name or "Unknown"} (Device {self.device_id}, ID: {self.device_user_id})>'

    def get_display_name(self):
        """Get display name for the device user"""
        return self.device_name or f"User {self.device_user_id}"


class EmployeeAttachment(db.Model):
    __tablename__ = 'employee_attachments'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)  # Original filename
    display_name = db.Column(db.String(255), nullable=False)  # User-defined name for the attachment
    file_path = db.Column(db.String(500), nullable=False)  # Path to the stored file
    file_size = db.Column(db.Integer, nullable=True)  # File size in bytes
    file_type = db.Column(db.String(100), nullable=True)  # MIME type
    description = db.Column(db.Text, nullable=True)  # Optional description
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)  # Admin who uploaded
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='attachments')
    uploader = db.relationship('User', foreign_keys=[uploaded_by], backref='uploaded_attachments')
    
    def __repr__(self):
        return f'<EmployeeAttachment {self.display_name} for User {self.user_id}>'

class LeaveType(db.Model):
    __tablename__ = 'leave_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(7), nullable=False, default='#007bff')  # Hex color for UI
    is_active = db.Column(db.Boolean, default=True)
    requires_balance = db.Column(db.Boolean, default=False)  # Whether this type requires leave balance
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<LeaveType {self.name}>'

class PaidHoliday(db.Model):
    __tablename__ = 'paid_holidays'
    
    id = db.Column(db.Integer, primary_key=True)
    holiday_type = db.Column(db.String(20), nullable=False, default='day')  # 'day' or 'range'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)  # Only for range type
    description = db.Column(db.String(255), nullable=False)
    is_recurring = db.Column(db.Boolean, default=False)  # For annual holidays
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    creator = db.relationship('User', backref='created_holidays')
    
    @property
    def date(self):
        """Backward compatibility - returns start_date for single day holidays"""
        return self.start_date
    
    @property
    def duration_days(self):
        """Calculate duration in days"""
        if self.holiday_type == 'day':
            return 1
        elif self.holiday_type == 'range' and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 1
    
    def __repr__(self):
        if self.holiday_type == 'day':
            return f'<PaidHoliday {self.start_date} - {self.description}>'
        else:
            return f'<PaidHoliday {self.start_date} to {self.end_date} - {self.description}>'

class LeaveBalance(db.Model):
    __tablename__ = 'leave_balances'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey('leave_types.id', ondelete='CASCADE'), nullable=False)
    total_days = db.Column(db.Integer, default=0)  # Total days allocated
    used_days = db.Column(db.Integer, default=0)   # Days used
    remaining_days = db.Column(db.Integer, default=0)  # Calculated field
    manual_remaining_days = db.Column(db.Integer, nullable=True)  # Manual override for remaining days
    year = db.Column(db.Integer, nullable=False, default=lambda: datetime.utcnow().year)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='leave_balances')
    leave_type = db.relationship('LeaveType', backref='balances')
    
    def calculate_remaining(self):
        """Calculate remaining days (allows negative values)"""
        if self.manual_remaining_days is not None:
            # Use manual override if set
            self.remaining_days = self.manual_remaining_days
        else:
            # Calculate automatically - allow negative values
            used_days = self.used_days or 0  # Handle None case
            self.remaining_days = self.total_days - used_days
        return self.remaining_days
    
    def __repr__(self):
        return f'<LeaveBalance User {self.user_id} - {self.leave_type.name} - {self.remaining_days} days>'


class DeletedUser(db.Model):
    """Model to track deleted users to prevent them from being recreated during sync"""
    __tablename__ = 'deleted_users'

    id = db.Column(db.Integer, primary_key=True)
    fingerprint_number = db.Column(db.String(50), nullable=False, unique=True)
    user_name = db.Column(db.String(100), nullable=True)  # Store the name for reference
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reason = db.Column(db.String(255), nullable=True)  # Optional reason for deletion
    
    # Relationships
    deleted_by_user = db.relationship('User', backref='deleted_users')
    
    # Indexes for better query performance
    __table_args__ = (
        Index('idx_deleted_user_fingerprint', 'fingerprint_number'),
        Index('idx_deleted_user_deleted_at', 'deleted_at'),
    )

    def __repr__(self):
        return f'<DeletedUser {self.fingerprint_number} - {self.user_name or "Unknown"}>'
