from flask_login import UserMixin
from datetime import datetime
from extensions import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    fingerprint_number = db.Column(db.String(50), nullable=True, unique=True)
    avaya_number = db.Column(db.String(50), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='employee')  # employee, manager, admin, general_manager, director
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    profile_picture = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, inactive
    joining_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    department = db.relationship('Department', foreign_keys=[department_id], backref='employees')
    leave_requests = db.relationship('LeaveRequest', backref='user', lazy=True, foreign_keys='LeaveRequest.user_id')
    permission_requests = db.relationship('PermissionRequest', backref='user', lazy=True, foreign_keys='PermissionRequest.user_id')
    notifications = db.relationship('Notification', backref='user', lazy=True)
    fingerprint_failures = db.relationship('FingerPrintFailure',
        primaryjoin="User.fingerprint_number==foreign(FingerPrintFailure.employee_id)",
        backref='user',
        lazy='dynamic'
    )
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_manager(self):
        return self.role == 'manager'
    
    def is_director(self):
        return self.role == 'director'
    
    def is_employee(self):
        return self.role == 'employee'
    
    def is_active(self):
        return self.status == 'active'
    
    def is_general_manager(self):
        return self.role == 'general_manager'
    
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

class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
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
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    reason = db.Column(db.Text, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    
    # Updated approval fields
    manager_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    manager_comment = db.Column(db.Text, nullable=True)
    manager_updated_at = db.Column(db.DateTime, nullable=True)
    
    admin_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_comment = db.Column(db.Text, nullable=True)
    admin_updated_at = db.Column(db.DateTime, nullable=True)
    
    general_manager_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    general_manager_comment = db.Column(db.Text, nullable=True)
    general_manager_updated_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def can_edit(self):
        return self.status == 'pending'
    
    def update_overall_status(self):
        """Update the overall status based on all approval levels"""
        if self.manager_status == 'rejected' or self.admin_status == 'rejected' or self.general_manager_status == 'rejected':
            self.status = 'rejected'
        elif self.manager_status == 'approved' and self.admin_status == 'approved' and self.general_manager_status == 'approved':
            self.status = 'approved'
        else:
            self.status = 'pending'
    
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
    
    # Updated approval fields
    manager_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    manager_comment = db.Column(db.Text, nullable=True)
    manager_updated_at = db.Column(db.DateTime, nullable=True)
    
    director_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    director_comment = db.Column(db.Text, nullable=True)
    director_updated_at = db.Column(db.DateTime, nullable=True)
    
    admin_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_comment = db.Column(db.Text, nullable=True)
    admin_updated_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def can_edit(self):
        return self.status == 'pending'
    
    def update_overall_status(self):
        """Update the overall status based on all approval levels"""
        if self.manager_status == 'rejected' or self.director_status == 'rejected' or self.admin_status == 'rejected':
            self.status = 'rejected'
        elif self.manager_status == 'approved' and self.director_status == 'approved' and self.admin_status == 'approved':
            self.status = 'approved'
        else:
            self.status = 'pending'
    
    def __repr__(self):
        return f"<PermissionRequest {self.id} - {self.status}>"

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # new_request, approval, rejection, comment
    status = db.Column(db.String(20), default='unread')  # unread, read
    reference_id = db.Column(db.Integer, nullable=True)  # ID of the related request
    reference_type = db.Column(db.String(20), nullable=True)  # leave, permission
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Notification {self.id} - {self.notification_type}>"

class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    device_ip = db.Column(db.String(15), nullable=False)  # Store the fingerprint device IP
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
    status = db.Column(db.String(20), default='present')  # present, absent, half-day, leave, permission
    status_reason = db.Column(db.String(100), nullable=True)  # Additional status context
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='daily_attendance')
    
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
    """Model for storing fingerprint device settings"""
    __tablename__ = 'device_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    device_ip = db.Column(db.String(15), nullable=False, default='192.168.11.2')
    device_port = db.Column(db.Integer, nullable=False, default=4370)
    device_name = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<DeviceSettings {self.device_ip}:{self.device_port}>'
