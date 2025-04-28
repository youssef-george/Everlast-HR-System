from datetime import datetime
from flask_login import UserMixin
from app import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='employee')  # employee, manager, admin, director
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    profile_picture = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    department = db.relationship('Department', foreign_keys=[department_id], backref='employees')
    leave_requests = db.relationship('LeaveRequest', backref='user', lazy=True, foreign_keys='LeaveRequest.user_id')
    permission_requests = db.relationship('PermissionRequest', backref='user', lazy=True, foreign_keys='PermissionRequest.user_id')
    notifications = db.relationship('Notification', backref='user', lazy=True)
    
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
    
    def __repr__(self):
        return f"<User {self.email}>"

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
    manager_approved = db.Column(db.Boolean, default=False)
    admin_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def can_edit(self):
        return self.status == 'pending'
    
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
    manager_approved = db.Column(db.Boolean, default=False)
    director_approved = db.Column(db.Boolean, default=False)
    admin_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def can_edit(self):
        return self.status == 'pending'
    
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
