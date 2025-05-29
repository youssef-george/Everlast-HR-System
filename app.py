import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
csrf = CSRFProtect()

# Create the app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SESSION_SECRET", "everlast_erp_default_secret")
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.environ.get("CSRF_SECRET", "everlast_erp_csrf_secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure the database - use SQLite for development, PostgreSQL for production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///everlast.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with the app
db.init_app(app)
login_manager.init_app(app)
csrf.init_app(app)

# Configure login manager
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Register blueprints
with app.app_context():
    # Import models first to ensure they're registered with SQLAlchemy
    from models import User, Department, LeaveRequest, PermissionRequest, Notification
    
    # Import and register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.departments import departments_bp
    from routes.leave import leave_bp
    from routes.permission import permission_bp
    from routes.calendar import calendar_bp
    from routes.profile import profile_bp
    from routes.notifications import notifications_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(permission_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(notifications_bp)
    
    # Create admin user if it doesn't exist
    from werkzeug.security import generate_password_hash
    
    db.create_all()
    
    # Create default admin user if doesn't exist
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

# Load user from database
@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Error handler for CSRF errors
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logging.error(f"CSRF error: {e}")
    return render_template('errors/csrf_error.html', reason=e.description), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
