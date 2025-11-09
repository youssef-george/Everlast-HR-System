import os
import logging
from dotenv import load_dotenv
from flask import Flask, redirect, url_for, flash, request, render_template, jsonify
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
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    Session(app)
    csrf = CSRFProtect(app)
    scheduler.init_app(app)
    
    # Log database connection info
    with app.app_context():
        logging.info(f"=== DATABASE CONNECTION ===")
        logging.info(f"Database URL: {db.engine.url}")
        logging.info(f"Database Driver: {db.engine.url.drivername}")
        logging.info(f"Database Host: {db.engine.url.host}")
        logging.info(f"Database Name: {db.engine.url.database}")
        logging.info(f"=============================")
    
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
                # Try parsing various datetime string formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S%z']:
                    try:
                        value = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    # Try ISO format
                    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return value
        if hasattr(value, 'strftime'):
            return value.strftime(format)
        return str(value)
    
    @app.template_filter('safe_datetime')
    def safe_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        """Safely format datetime, handling both string and datetime objects"""
        if value is None:
            return ''
        # If it's already a datetime object, format it
        if hasattr(value, 'strftime'):
            return value.strftime(format)
        # If it's a string, try to parse and format it
        if isinstance(value, str):
            try:
                # Try parsing various datetime string formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S.%f']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.strftime(format)
                    except ValueError:
                        continue
                # Try ISO format
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.strftime(format)
            except (ValueError, AttributeError):
                return value
        return str(value)
    
    @app.template_filter('to_datetime')
    def to_datetime(value):
        """Convert string to datetime object for template arithmetic"""
        if value is None:
            return None
        # If it's already a datetime object, return it
        if isinstance(value, datetime):
            return value
        # If it's a string, try to parse it
        if isinstance(value, str):
            try:
                # Try parsing various datetime string formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S.%f']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
                # Try ISO format
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return None
        return None
    
    @app.template_filter('hours_minutes')
    def format_hours_minutes_filter(hours):
        """Template filter to convert decimal hours to 'Xh Ym' format."""
        from helpers import format_hours_minutes
        return format_hours_minutes(hours)
    
    # Add template context processor for datetime
    @app.context_processor
    def utility_processor():
        return {'now': datetime.now()}
    
    # Quick fix for missing table and sequence - run once at startup
    _tables_initialized = False
    
    def ensure_tables_exist():
        """Ensure critical tables exist and sequences are fixed - runs once"""
        nonlocal _tables_initialized
        if _tables_initialized:
            return
        _tables_initialized = True
        try:
            from sqlalchemy import text
            
            # Create employee_attachments table if missing
            try:
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS employee_attachments (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        file_name VARCHAR(255) NOT NULL,
                        display_name VARCHAR(255) NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        file_size INTEGER,
                        file_type VARCHAR(100),
                        description TEXT,
                        uploaded_by INTEGER,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        CONSTRAINT fk_employee_attachments_user 
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        CONSTRAINT fk_employee_attachments_uploader 
                            FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL
                    )
                """))
                db.session.commit()
                logging.info("✅ employee_attachments table checked/created")
            except Exception as e:
                logging.warning(f"employee_attachments table check: {e}")
                db.session.rollback()
            
            # Fix Department sequence
            try:
                result = db.session.execute(text("SELECT COALESCE(MAX(id), 0) FROM departments"))
                max_id = result.scalar() or 0
                
                # Ensure sequence exists and is linked
                db.session.execute(text("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_sequences WHERE sequencename = 'departments_id_seq') THEN
                            CREATE SEQUENCE departments_id_seq;
                        END IF;
                    END $$;
                """))
                db.session.execute(text("ALTER TABLE departments ALTER COLUMN id SET DEFAULT nextval('departments_id_seq')"))
                db.session.execute(text("ALTER SEQUENCE departments_id_seq OWNED BY departments.id"))
                db.session.execute(text(f"SELECT setval('departments_id_seq', GREATEST({max_id}, 1), false)"))
                db.session.commit()
                logging.info(f"✅ Department sequence fixed")
            except Exception as e:
                logging.warning(f"Department sequence fix: {e}")
                db.session.rollback()
                
        except Exception as e:
            logging.warning(f"Table/sequence check: {e}")
            db.session.rollback()
    
    # Run on first request
    @app.before_request
    def before_request_ensure_tables():
        ensure_tables_exist()
    
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
        from routes.attendance import attendance_bp
        from routes.paid_holidays import paid_holidays_bp
        from routes.api import api_bp
        from routes.final_report import final_report_bp
        
        # Register blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(departments_bp)
        app.register_blueprint(leave_bp)
        app.register_blueprint(permission_bp)
        app.register_blueprint(calendar_bp)
        app.register_blueprint(profile_bp)
        app.register_blueprint(attendance_bp)
        app.register_blueprint(paid_holidays_bp, url_prefix='/paid-holidays')
        app.register_blueprint(api_bp)
        app.register_blueprint(final_report_bp)
        
        # Initialize database
        # db.create_all()  # Commented out - using migrations instead
        
        # Create default admin user if doesn't exist
        # from models import User
        # admin_email = 'erp@everlastwellness.com'
        # admin = User.query.filter_by(email=admin_email).first()
        # if not admin:
        #     logging.info("Creating default admin user")
        #     admin = User(
        #         first_name="ERP",
        #         last_name="Admin",
        #         email=admin_email,
        #         password_hash=generate_password_hash("Everlast@123"),
        #         role="admin",
        #         status="active"
        #     )
        #     db.session.add(admin)
        #     db.session.commit()
    
    # Configure scheduler
    app.config['SCHEDULER_API_ENABLED'] = True
    app.config['SCHEDULER_TIMEZONE'] = 'UTC'
    
    # Auto-sync disabled - manual sync only
    # @scheduler.task('interval', id='sync_attendance', minutes=1, misfire_grace_time=300, coalesce=True, max_instances=1)
    # def scheduled_sync():
    #     with app.app_context():
    #         try:
    #             from routes.attendance import sync_attendance_task
    #             logging.info('Starting scheduled attendance sync...')
    #             sync_stats = sync_attendance_task(full_sync=True)
    #             if sync_stats:
    #                 logging.info(f"Scheduled sync completed. Added {sync_stats['records_added']} records and updated {sync_stats.get('records_updated', 0)} records.")
    #         except Exception as e:
    #             logging.error(f'Scheduled sync failed: {str(e)}')

    # scheduler.start()  # Disabled auto-sync
    
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
    
    @app.route('/health')
    def health_check():
        """Health check endpoint to monitor database connection pool status"""
        try:
            from extensions import db
            from sqlalchemy import text
            
            # Test primary database connection
            db.session.execute(text('SELECT 1'))
            
            # Get connection pool status
            pool = db.engine.pool
            pool_status = {
                'pool_size': getattr(pool, 'size', lambda: 'N/A')(),
                'checked_in': getattr(pool, 'checkedin', lambda: 'N/A')(),
                'checked_out': getattr(pool, 'checkedout', lambda: 'N/A')(),
                'overflow': getattr(pool, 'overflow', lambda: 'N/A')()
            }
            
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'pool_status': pool_status
            }), 200
            
        except Exception as e:
            logging.error(f"Health check failed: {str(e)}")
            return jsonify({
                'status': 'unhealthy',
                'primary_database': 'disconnected',
                'postgres_database': 'unknown',
                'error': str(e)
            }), 500
    
    @app.teardown_appcontext
    def close_db(error):
        """Ensure database connections are properly closed"""
        try:
            if error:
                db.session.rollback()
            db.session.close()
        except Exception as e:
            logging.warning(f"Error closing database session: {str(e)}")
    
    @app.errorhandler(500)
    def handle_internal_error(e):
        """Handle internal errors and rollback transactions"""
        try:
            db.session.rollback()
        except Exception:
            pass
        
        # Log the full error with traceback
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Internal error: {str(e)}", exc_info=True)
        logging.error(f"Full traceback:\n{error_details}")
        
        # Get original exception if available
        original_error = str(e)
        if hasattr(e, 'original_exception') and e.original_exception:
            original_error = str(e.original_exception)
        
        # Return JSON for API requests (POST requests, JSON accept header, or API routes)
        is_api_request = (
            request.method == 'POST' or 
            request.accept_mimetypes.accept_json or
            request.path.startswith('/attendance/') or
            request.path.startswith('/api/')
        )
        
        if is_api_request:
            error_message = original_error
            # In development, include more details
            if app.config.get('DEBUG', False):
                error_message = f"{original_error}\n\nTraceback:\n{error_details}"
            return jsonify({
                'status': 'error',
                'message': f'Internal server error: {original_error}',
                'details': error_details if app.config.get('DEBUG', False) else None
            }), 500
        
        # Return HTML for regular page requests
        if app.config.get('DEBUG', False):
            return f"<h1>Internal Server Error</h1><pre>{error_details}</pre>", 500
        return "Internal Server Error", 500
    
    return app

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Use PORT env variable if exists
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=port)
