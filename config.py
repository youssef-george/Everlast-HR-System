import os
from dotenv import load_dotenv

# Load environment variables before defining config
load_dotenv()

class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    WTF_CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET') or 'your-csrf-secret-here'
    WTF_CSRF_ENABLED = True
    
    # PostgreSQL Database Configuration (Primary)
    # SSL mode: require (as per Coolify requirements)
    # Get DATABASE_URL from environment, with fallback to default
    _default_db_url = 'postgresql+psycopg2://postgres:1TJQKLGMKdZisAEtJ96ZQC9vh9iZL8zvnrqAXLZOanFANPy5QSHgW4uCm7PA4oRq@196.219.160.253:5444/postgres?sslmode=require'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or _default_db_url
    
    # Validate DATABASE_URL doesn't contain device IP (common misconfiguration)
    if '192.168.11.253' in SQLALCHEMY_DATABASE_URI:
        import warnings
        warnings.warn(
            f"WARNING: DATABASE_URL appears to use device IP (192.168.11.253). "
            f"Using default database URL instead. Current DATABASE_URL: {SQLALCHEMY_DATABASE_URI[:50]}..."
        )
        SQLALCHEMY_DATABASE_URI = _default_db_url
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # PostgreSQL engine options with improved timeout settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_reset_on_return": "rollback",
        "echo": False,
        "connect_args": {
            "sslmode": "require",
            "connect_timeout": 10,  # Connection timeout in seconds
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
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