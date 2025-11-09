import os
from dotenv import load_dotenv

# Load environment variables before defining config
load_dotenv()

class Config:
    # ------------------------
    # Basic Flask configuration
    # ------------------------
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here')
    WTF_CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET', 'your-csrf-secret-here')
    WTF_CSRF_ENABLED = True

    # ------------------------
    # Database Configuration
    # ------------------------
    # Use only the environment DATABASE_URL (Coolify will inject this)
    # Fallback ONLY for local development
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:password@localhost:5432/postgres'
    )

    # Clean dialect if someone uses postgres:// instead of postgresql://
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Engine options with increased timeouts for network latency
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 3600,
        "pool_pre_ping": True,  # Verify connections before using
        "pool_size": 5,  # Reduced pool size for better connection management
        "max_overflow": 10,
        "pool_timeout": 60,  # Increased timeout for pool connections
        "pool_reset_on_return": "rollback",
        "echo": False,
        "connect_args": {
            "connect_timeout": 30,  # Increased connection timeout to 30 seconds
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    }

    # ------------------------
    # File upload configuration
    # ------------------------
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # ------------------------
    # Server Settings
    # ------------------------
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = 5000

    # ------------------------
    # Session Configuration
    # ------------------------
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        'flask_session_data'
    )
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = 1800  # 30 minutes

    # ------------------------
    # Scheduler
    # ------------------------
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "Asia/Kolkata"
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': False,
        'max_instances': 1
    }

    # ------------------------
    # Attendance Device Settings (Legacy)
    # ------------------------
    DEVICE_IP = os.environ.get('DEVICE_IP', '192.168.11.253')
    DEVICE_PORT = int(os.environ.get('DEVICE_PORT', '4370'))
    DEVICE_URL = os.environ.get('DEVICE_URL', 'http://192.168.11.253/')

    # ------------------------
    # Sync Agent
    # ------------------------
    SYNC_SECRET = os.environ.get('SYNC_SECRET', 'your-sync-secret-key')
    ENABLE_DIRECT_DEVICE_SYNC = os.environ.get(
        'ENABLE_DIRECT_DEVICE_SYNC', 'false'
    ).lower() == 'true'

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
