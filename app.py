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
    
    # Initialize security middleware
    from security import setup_security_middleware
    setup_security_middleware(app)
    
    # Log database connection info and validate connection
    with app.app_context():
        db_url = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')
        # Mask password in logs
        if '@' in db_url:
            parts = db_url.split('@')
            if len(parts) > 1:
                masked_url = parts[0].split('//')[0] + '//***@' + parts[1]
            else:
                masked_url = db_url
        else:
            masked_url = db_url
        
        logging.info(f"=== DATABASE CONNECTION ===")
        logging.info(f"Database URL: {masked_url}")
        logging.info(f"Database Driver: {db.engine.url.drivername}")
        logging.info(f"Database Host: {db.engine.url.host}")
        logging.info(f"Database Port: {db.engine.url.port}")
        logging.info(f"Database Name: {db.engine.url.database}")
        
        # Validate database URL doesn't use device IP
        if '192.168.11.253' in db_url:
            logging.error("⚠️  WARNING: Database URL appears to use device IP (192.168.11.253)")
            logging.error("⚠️  This is likely a misconfiguration. Check your DATABASE_URL environment variable.")
        
        # Test database connection with retry logic
        max_retries = 3
        retry_delay = 5  # seconds
        connection_successful = False
        
        for attempt in range(1, max_retries + 1):
            try:
                from sqlalchemy import text
                db.session.execute(text('SELECT 1'))
                db.session.commit()
                logging.info("✅ Database connection test successful")
                connection_successful = True
                break
            except Exception as e:
                if attempt < max_retries:
                    logging.warning(f"⚠️  Database connection attempt {attempt}/{max_retries} failed: {str(e)}")
                    logging.info(f"⏳ Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logging.error(f"❌ Database connection test failed after {max_retries} attempts: {str(e)}")
                    logging.error("⚠️  The application will start but may not work correctly. Please check:")
                    logging.error("   1. DATABASE_URL environment variable is set correctly")
                    logging.error("   2. Database server is accessible from this host")
                    logging.error("   3. Network/firewall allows connections to the database")
                    logging.error("   4. Database server is running and accepting connections")
                    logging.warning("⚠️  Application will continue to start. Database connections will be retried on first request.")
        
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
    
    # Make config available to templates
    @app.context_processor
    def inject_config():
        # Smart detection: Check if we're in production based on request hostname
        def is_production():
            """Detect production environment based on request hostname"""
            # Check explicit environment variable first
            env_override = os.environ.get('TURNSTILE_ENABLED', '').lower()
            if env_override in ['true', 'false']:
                return env_override == 'true'
            
            # Check if DEBUG is disabled
            if not app.config.get('DEBUG', True):
                return True
            
            # Check FLASK_ENV
            flask_env = os.environ.get('FLASK_ENV', '').lower()
            if flask_env == 'production':
                return True
            if flask_env == 'development':
                return False
            
            # Check request hostname (if available)
            try:
                from flask import request
                if request and hasattr(request, 'host'):
                    hostname = request.host.lower()
                    # Local development indicators
                    local_indicators = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
                    if any(indicator in hostname for indicator in local_indicators):
                        return False
                    # Production domain indicators
                    production_domains = ['everlastdashboard.com', 'hr.everlastdashboard.com']
                    if any(domain in hostname for domain in production_domains):
                        return True
            except:
                pass
            
            # Default: assume local/development
            return False
        
        # Update Turnstile enabled status based on smart detection
        turnstile_enabled = is_production()
        app.config['TURNSTILE_ENABLED'] = turnstile_enabled
        
        return dict(
            config=app.config,
            is_production=is_production
        )
    
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
            from psycopg2 import OperationalError
            from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
            
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
            except (OperationalError, SQLAlchemyOperationalError) as e:
                # Connection errors - don't log as warning, just skip silently
                # The connection will be retried on actual database operations
                db.session.rollback()
                return  # Skip remaining operations if we can't connect
            except Exception as e:
                logging.warning(f"employee_attachments table check: {e}")
                db.session.rollback()
            
            # Break tables removed
            
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
            except (OperationalError, SQLAlchemyOperationalError) as e:
                # Connection errors - skip silently
                db.session.rollback()
            except Exception as e:
                logging.warning(f"Department sequence fix: {e}")
                db.session.rollback()
                
        except (OperationalError, SQLAlchemyOperationalError) as e:
            # Connection errors - skip silently, connection will be retried later
            try:
                db.session.rollback()
            except:
                pass
        except Exception as e:
            logging.warning(f"Table/sequence check: {e}")
            try:
                db.session.rollback()
            except:
                pass
    
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
    
    # Auto-sync enabled - sync every 45 seconds
    @scheduler.task('interval', id='sync_attendance', seconds=45, misfire_grace_time=300, coalesce=True, max_instances=1)
    def scheduled_sync():
        with app.app_context():
            try:
                from routes.attendance import sync_attendance_task
                logging.info('Starting scheduled attendance sync...')
                sync_stats = sync_attendance_task(full_sync=True)
                if sync_stats:
                    logging.info(f"Scheduled sync completed. Added {sync_stats.get('records_added', 0)} records and updated {sync_stats.get('records_updated', 0)} records.")
            except Exception as e:
                logging.error(f'Scheduled sync failed: {str(e)}')

    scheduler.start()  # Enable auto-sync
    
    @app.route('/')
    def root():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))
    
    @app.route('/robots.txt')
    def robots_txt():
        """Serve robots.txt to prevent scraping"""
        from flask import send_from_directory
        return send_from_directory(app.static_folder, 'robots.txt')
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logging.error(f"CSRF error: {e}")
        flash('Your session has expired or is invalid. Please log in again.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Handle database connection errors specifically
    @app.errorhandler(500)
    def handle_internal_error(e):
        """Handle internal errors including database connection issues"""
        from psycopg2 import OperationalError
        from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError
        
        # Check if it's a database connection error
        error_str = str(e)
        is_db_error = (
            isinstance(e, (OperationalError, SQLAlchemyOperationalError)) or 
            ('connection' in error_str.lower() and 'timeout' in error_str.lower()) or
            ('psycopg2.OperationalError' in error_str) or
            ('connection to server' in error_str.lower())
        )
        
        if is_db_error:
            logging.error(f"Database connection error: {str(e)}")
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set')
            # Mask password in logs
            if '@' in db_url:
                parts = db_url.split('@')
                if len(parts) > 1:
                    db_url = parts[0].split('//')[0] + '//***@' + parts[1]
            logging.error(f"Database URL being used: {db_url[:100]}...")
            
            # Extract host and port from error if available
            import re
            host_match = re.search(r'at "([^"]+)"', error_str)
            port_match = re.search(r'port (\d+)', error_str)
            host_info = ""
            if host_match and port_match:
                host_info = f" (Host: {host_match.group(1)}, Port: {port_match.group(1)})"
            
            # Try to rollback any pending transaction
            try:
                db.session.rollback()
            except Exception:
                pass
            
            # If user is authenticated, show error message
            if current_user.is_authenticated:
                error_message = "Database connection failed"
                error_details = f"Unable to connect to the database server.{host_info}\n\n"
                error_details += "Possible causes:\n"
                error_details += "• Database server is down or unreachable\n"
                error_details += "• Network/firewall is blocking the connection\n"
                error_details += "• VPN not connected (if required)\n"
                error_details += "• Incorrect database host/port in configuration\n\n"
                error_details += "Please contact your system administrator."
                
                flash('Database connection failed. Please contact the administrator.', 'danger')
                return render_template('error.html', 
                    error_message=error_message,
                    error_details=error_details if app.config.get('DEBUG') else "Unable to connect to database. Please try again later."
                ), 503
            
            # If not authenticated, redirect to login with error
            flash('Database connection error. Please try again later.', 'danger')
            return redirect(url_for('auth.login'))
        
        # For other 500 errors, use default handling
        try:
            db.session.rollback()
        except Exception:
            pass
        
        # Log the full error with traceback
        import traceback
        logging.error(f"Internal server error: {str(e)}")
        logging.error(traceback.format_exc())
        
        return render_template('error.html', 
            error_message="An internal error occurred",
            error_details=str(e) if app.config.get('DEBUG') else "Please try again later."
        ), 500
    
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
    
    return app

if __name__ == '__main__':
    import socket
    
    port = int(os.environ.get("PORT", 5000))  # Use PORT env variable if exists
    app = create_app()
    
    # Get local IP addresses for network access
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
            except Exception:
                ip = '127.0.0.1'
            finally:
                s.close()
            return ip
        except Exception:
            return '127.0.0.1'
    
    local_ip = get_local_ip()
    
    # Print network access information
    import sys
    import io
    # Set UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    try:
        print("\n" + "=" * 70)
        print("EverLast ERP Server Starting")
        print("=" * 70)
        print(f"\nServer Configuration:")
        print(f"   - Host: 0.0.0.0 (Listening on all network interfaces)")
        print(f"   - Port: {port}")
        print(f"\nNetwork Access URLs:")
        print(f"   - Local:     http://localhost:{port}")
        print(f"   - Local:     http://127.0.0.1:{port}")
        if local_ip != '127.0.0.1':
            print(f"   - Network:   http://{local_ip}:{port}")
        print(f"\nLogin URL:")
        if local_ip != '127.0.0.1':
            print(f"   - http://{local_ip}:{port}/auth/login")
        print(f"   - http://localhost:{port}/auth/login")
        print(f"\nTo access from other devices on your network:")
        print(f"   1. Make sure Windows Firewall allows port {port}")
        print(f"   2. Use the Network URL above from any device on the same network")
        print(f"   3. All devices must be on the same local network (same router)")
        print("\n" + "=" * 70 + "\n")
    except UnicodeEncodeError:
        # Fallback without emojis if encoding still fails
        print("\n" + "=" * 70)
        print("EverLast ERP Server Starting")
        print("=" * 70)
        print(f"\nServer Configuration:")
        print(f"   - Host: 0.0.0.0 (Listening on all network interfaces)")
        print(f"   - Port: {port}")
        print(f"\nNetwork Access URLs:")
        print(f"   - Local:     http://localhost:{port}")
        print(f"   - Local:     http://127.0.0.1:{port}")
        if local_ip != '127.0.0.1':
            print(f"   - Network:   http://{local_ip}:{port}")
        print(f"\nLogin URL:")
        if local_ip != '127.0.0.1':
            print(f"   - http://{local_ip}:{port}/auth/login")
        print(f"   - http://localhost:{port}/auth/login")
        print(f"\nTo access from other devices on your network:")
        print(f"   1. Make sure Windows Firewall allows port {port}")
        print(f"   2. Use the Network URL above from any device on the same network")
        print(f"   3. All devices must be on the same local network (same router)")
        print("\n" + "=" * 70 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)

