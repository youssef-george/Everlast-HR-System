import os
import logging
from dotenv import load_dotenv
from flask import Flask, redirect, url_for, flash, request, render_template
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash
from config import config
from extensions import db, scheduler
from routes.attendance import sync_attendance_task
from flask_apscheduler import APScheduler
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize scheduler
scheduler = APScheduler()

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Load config
    app.config.from_object(config[config_name])
    print(f"DEBUG: SECRET_KEY = {app.config.get('SECRET_KEY')}")
    print(f"DEBUG: WTF_CSRF_SECRET_KEY = {app.config.get('WTF_CSRF_SECRET_KEY')}")
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    Session(app)
    csrf = CSRFProtect(app)
    scheduler.init_app(app)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    # Add template filters
    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        if value is None:
            return ''
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return value
        return value.strftime(format)
    
    # Add template context processor for datetime
    @app.context_processor
    def utility_processor():
        return {'now': datetime.now()}
    
    def admin_instance_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not app.config.get('IS_ADMIN_INSTANCE', False):
                flash('This feature is only available on the admin portal.', 'error')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    
    # Register blueprints
    with app.app_context():
        from routes.auth import auth_bp
        from routes.dashboard import dashboard_bp
        from routes.departments import departments_bp
        from routes.leave import leave_bp
        from routes.permission import permission_bp
        from routes.calendar import calendar_bp
        from routes.profile import profile_bp
        from routes.notifications import notifications_bp
        from routes.attendance import attendance_bp
        
        # Register blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(departments_bp)
        app.register_blueprint(leave_bp)
        app.register_blueprint(permission_bp)
        app.register_blueprint(calendar_bp)
        app.register_blueprint(profile_bp)
        app.register_blueprint(notifications_bp)
        app.register_blueprint(attendance_bp)
        
        # Initialize database
        db.create_all()
        
        # Create default admin user if doesn't exist
        from models import User
        admin_email = 'erp@everlastwellness.com'
        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            logging.info("Creating default admin user")
            admin = User(
                first_name="ERP",
                last_name="Admin",
                email=admin_email,
                password_hash=generate_password_hash("Everlast@123"),
                role="admin",
                status="active"
            )
            db.session.add(admin)
            db.session.commit()
    
    # Configure scheduler
    app.config['SCHEDULER_API_ENABLED'] = True
    app.config['SCHEDULER_TIMEZONE'] = 'UTC'
    
    @scheduler.task('interval', id='sync_attendance', seconds=60, misfire_grace_time=3600, coalesce=True, max_instances=1)
    def scheduled_sync():
        with app.app_context():
            try:
                from routes.attendance import sync_attendance_task
                logging.info('Starting scheduled attendance sync...')
                sync_stats = sync_attendance_task()
                if sync_stats:
                    logging.info(f"Scheduled sync completed. Added {sync_stats['records_added']} records.")
            except Exception as e:
                logging.error(f'Scheduled sync failed: {str(e)}')

    scheduler.start()
    
    @app.route('/')
    def root():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logging.error(f"CSRF error: {e}")
        flash('Your session has expired or is invalid. Please log in again.', 'danger')
        return redirect(url_for('auth.login'))
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
