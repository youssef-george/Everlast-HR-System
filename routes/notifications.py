from flask import Blueprint, render_template, redirect, url_for, jsonify, request
from flask_login import login_required, current_user
from models import Notification
from app import db

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('/')
@login_required
def index():
    """Show all notifications for the current user"""
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    
    # Mark all as read
    for notification in notifications:
        if notification.status == 'unread':
            notification.status = 'read'
    
    db.session.commit()
    
    return render_template('notifications/index.html', 
                           title='Notifications', 
                           notifications=notifications)

@notifications_bp.route('/unread_count')
@login_required
def unread_count():
    """Get count of unread notifications for the current user"""
    count = Notification.query.filter_by(user_id=current_user.id, status='unread').count()
    return jsonify({'count': count})

@notifications_bp.route('/mark_as_read/<int:id>', methods=['POST'])
@login_required
def mark_as_read(id):
    """Mark a specific notification as read"""
    notification = Notification.query.get_or_404(id)
    
    # Check if the notification belongs to the current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    notification.status = 'read'
    db.session.commit()
    
    return jsonify({'success': True})

@notifications_bp.route('/mark_all_as_read', methods=['POST'])
@login_required
def mark_all_as_read():
    """Mark all notifications for the current user as read"""
    notifications = Notification.query.filter_by(user_id=current_user.id, status='unread').all()
    
    for notification in notifications:
        notification.status = 'read'
    
    db.session.commit()
    
    return jsonify({'success': True})

@notifications_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    """Delete a specific notification"""
    notification = Notification.query.get_or_404(id)
    
    # Check if the notification belongs to the current user
    if notification.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({'success': True})

@notifications_bp.route('/get_recent', methods=['GET'])
@login_required
def get_recent():
    """Get recent unread notifications for displaying in the navbar"""
    notifications = Notification.query.filter_by(
        user_id=current_user.id, 
        status='unread'
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    result = []
    for notification in notifications:
        result.append({
            'id': notification.id,
            'message': notification.message,
            'type': notification.notification_type,
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M'),
            'reference_id': notification.reference_id,
            'reference_type': notification.reference_type
        })
    
    return jsonify(result)
