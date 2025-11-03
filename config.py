import os
from dotenv import load_dotenv

# Load environment variables before defining config
load_dotenv()

class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    WTF_CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET') or 'your-csrf-secret-here'
    WTF_CSRF_ENABLED = True
    
    # Dual Database Configuration
    # Primary database (SQLite) - used for main operations during transition
    _base_dir = os.path.abspath(os.path.dirname(__file__))
    _sqlite_path = os.path.join(_base_dir, 'instance', 'everlast.db')
    # Convert Windows backslashes to forward slashes for SQLite URI
    _sqlite_path_uri = _sqlite_path.replace('\\', '/')
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLITE_DATABASE_URL') or f'sqlite:///{_sqlite_path_uri}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # PostgreSQL database configuration for sync
    POSTGRES_DATABASE_URI = os.environ.get('POSTGRES_DATABASE_URL') or \
        'postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require'
    
    # Database binds for multiple databases
    SQLALCHEMY_BINDS = {
        'postgres': POSTGRES_DATABASE_URI
    }
    
    # Database sync configuration
    ENABLE_DB_SYNC = os.environ.get('ENABLE_DB_SYNC', 'true').lower() == 'true'
    SYNC_BATCH_SIZE = int(os.environ.get('SYNC_BATCH_SIZE', '100'))
    SYNC_RETRY_ATTEMPTS = int(os.environ.get('SYNC_RETRY_ATTEMPTS', '3'))
    SYNC_RETRY_DELAY = int(os.environ.get('SYNC_RETRY_DELAY', '5'))  # seconds
    
    # Primary database engine options (SQLite)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "echo": False,
        "connect_args": {
            "timeout": 20,
            "check_same_thread": False
        }
    }
    
    # PostgreSQL engine options
    POSTGRES_ENGINE_OPTIONS = {
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_reset_on_return": "rollback",
        "echo": False,
    }
    
    # File upload configuration
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Server port
    PORT = 5000
    
    # Admin instance flag
    IS_ADMIN_INSTANCE = True
    
    # Session configuration
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'flask_session_data')
    PERMANENT_SESSION_LIFETIME = 1800  # 30 minutes
    SESSION_PERMANENT = True
    
    # Scheduler configuration
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "Asia/Kolkata"
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': False,
        'max_instances': 1
    }
    
    # Server configuration
    HOST = os.environ.get('HOST', '127.0.0.1')
    
    # Device configuration for attendance data fetching (Legacy - now handled by sync agent)
    DEVICE_IP = os.environ.get('DEVICE_IP', '192.168.11.253')
    DEVICE_PORT = int(os.environ.get('DEVICE_PORT', '4370'))
    DEVICE_URL = os.environ.get('DEVICE_URL', 'http://192.168.11.253/')
    
    # Sync Agent Configuration
    SYNC_SECRET = os.environ.get('SYNC_SECRET', 'your-sync-secret-key')
    ENABLE_DIRECT_DEVICE_SYNC = os.environ.get('ENABLE_DIRECT_DEVICE_SYNC', 'false').lower() == 'true'
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
    WTF_CSRF_ENABLED = True
    PREFERRED_URL_SCHEME = 'https'
    
    # Session cookie security for HTTPS deployment
    SESSION_COOKIE_SECURE = True  # Cookies only sent over HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    
    # Flask-Login cookie security
    REMEMBER_COOKIE_SECURE = True  # Remember me cookie secure
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}