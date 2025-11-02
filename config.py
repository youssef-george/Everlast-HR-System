import os

class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    WTF_CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET') or 'your-csrf-secret-here'
    WTF_CSRF_ENABLED = True
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///everlast.db?timeout=10000'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Database engine options - conditional based on database type
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///everlast.db?timeout=10000')
    if _db_url.startswith('postgresql://') or _db_url.startswith('postgres://'):
        # PostgreSQL configuration
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_reset_on_return": "rollback",
            "echo": False,
        }
    else:
        # SQLite configuration
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_reset_on_return": "rollback",
            "echo": False,
            "connect_args": {
                "timeout": 20,
                "check_same_thread": False
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
    
    # Device configuration for attendance data fetching
    DEVICE_IP = os.environ.get('DEVICE_IP', '192.168.11.253')
    DEVICE_PORT = int(os.environ.get('DEVICE_PORT', '4370'))
    DEVICE_URL = os.environ.get('DEVICE_URL', 'http://192.168.11.253/')
    
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