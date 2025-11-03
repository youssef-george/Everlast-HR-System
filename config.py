import os
from dotenv import load_dotenv

# Load environment variables before defining config
load_dotenv()

class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    WTF_CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET') or 'your-csrf-secret-here'
    WTF_CSRF_ENABLED = True
    
    # PostgreSQL as Primary Database Configuration
    # DATABASE_URL takes precedence, then POSTGRES_DATABASE_URL, then default connection
    DATABASE_URL = os.environ.get('DATABASE_URL') or \
                   os.environ.get('POSTGRES_DATABASE_URL') or \
                   'postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require'
    
    # Primary database URI - PostgreSQL
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # SQLite backup/legacy path (for migration only, not used as primary)
    _base_dir = os.path.abspath(os.path.dirname(__file__))
    _sqlite_path = os.path.join(_base_dir, 'instance', 'everlast.db')
    _sqlite_path_uri = _sqlite_path.replace('\\', '/')
    SQLITE_BACKUP_URI = os.environ.get('SQLITE_DATABASE_URL') or f'sqlite:///{_sqlite_path_uri}'
    
    # Database binds (keep for legacy support if needed, but primary is PostgreSQL)
    SQLALCHEMY_BINDS = {}
    
    # Database sync configuration (DISABLED - PostgreSQL is now primary, no sync needed)
    ENABLE_DB_SYNC = False  # Disabled since PostgreSQL is primary
    
    # Primary database engine options (PostgreSQL)
    # Build connect_args based on DATABASE_URL
    connect_args = {}
    if "sslmode=require" in DATABASE_URL or "sslmode=prefer" in DATABASE_URL:
        connect_args["sslmode"] = "require"
    
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_size": 10,  # Pool size for connections
        "max_overflow": 20,  # Max overflow connections
        "pool_timeout": 30,  # Timeout for getting connection from pool
        "pool_reset_on_return": "rollback",
        "echo": False,
        "connect_args": {
            **connect_args,
            "connect_timeout": 10,  # Connection timeout in seconds
            "command_timeout": 30,  # Query timeout in seconds
            "application_name": "everlast_erp"  # Helpful for database monitoring
        }
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
    
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}