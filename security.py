"""
Security Module for EverLast ERP
Implements comprehensive security measures for public deployment
"""
import os
import re
import time
import hashlib
from functools import wraps
from flask import request, jsonify, abort, g, current_app
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import logging

# Rate limiting storage (in production, use Redis)
_rate_limit_storage = {}
_rate_limit_cleanup_interval = 300  # 5 minutes

# Bot detection patterns
SUSPICIOUS_USER_AGENTS = [
    'bot', 'crawler', 'spider', 'scraper', 'curl', 'wget', 
    'python-requests', 'scrapy', 'httpx', 'go-http-client',
    'java/', 'apache-httpclient', 'okhttp'
]

# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'},
    'documents': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.rtf'},
    'archives': {'.zip', '.rar', '.7z', '.tar', '.gz'}
}

ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp',
    'application/pdf', 'application/msword', 
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain', 'application/rtf',
    'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed'
}


def setup_security_headers(app):
    """Configure security headers for all responses"""
    @app.after_request
    def set_security_headers(response):
        """Add security headers to all responses"""
        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'DENY'
        
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # XSS Protection (legacy, but still useful)
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://code.jquery.com https://challenges.cloudflare.com https://cdn.datatables.net https://cdn.ckeditor.com; "
            "script-src-elem 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://code.jquery.com https://challenges.cloudflare.com https://cdn.datatables.net https://cdn.ckeditor.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.datatables.net https://cdn.ckeditor.com; "
            "style-src-elem 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.datatables.net https://cdn.ckeditor.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.ckeditor.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://challenges.cloudflare.com https://cdn.datatables.net https://cdn.ckeditor.com; "
            "frame-src 'self' https://challenges.cloudflare.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "upgrade-insecure-requests;"
        )
        response.headers['Content-Security-Policy'] = csp
        
        # Permissions Policy (formerly Feature Policy) - Removed 'speaker' as it's not a valid feature
        response.headers['Permissions-Policy'] = (
            'geolocation=(), microphone=(), camera=(), payment=(), usb=(), '
            'magnetometer=(), gyroscope=()'
        )
        
        # HSTS (only if HTTPS)
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Remove server information
        response.headers.pop('Server', None)
        
        return response


def rate_limit(max_requests=100, window=60, per_ip=True):
    """
    Rate limiting decorator
    
    Args:
        max_requests: Maximum number of requests allowed
        window: Time window in seconds
        per_ip: If True, rate limit per IP; if False, per user
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get identifier (IP or user ID)
            if per_ip:
                identifier = request.remote_addr or request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
            else:
                from flask_login import current_user
                identifier = current_user.id if current_user.is_authenticated else request.remote_addr
            
            if not identifier:
                abort(429)
            
            # Clean old entries periodically
            current_time = time.time()
            if hasattr(g, '_last_rate_limit_cleanup'):
                if current_time - g._last_rate_limit_cleanup > _rate_limit_cleanup_interval:
                    cleanup_rate_limit_storage()
                    g._last_rate_limit_cleanup = current_time
            else:
                g._last_rate_limit_cleanup = current_time
            
            # Check rate limit
            key = f"{f.__name__}:{identifier}"
            now = time.time()
            
            if key in _rate_limit_storage:
                requests, first_request_time = _rate_limit_storage[key]
                
                # Reset if window has passed
                if now - first_request_time > window:
                    _rate_limit_storage[key] = (1, now)
                else:
                    if requests >= max_requests:
                        logging.warning(f"Rate limit exceeded for {identifier} on {f.__name__}")
                        return jsonify({
                            'error': 'Rate limit exceeded',
                            'message': f'Too many requests. Please try again in {int(window - (now - first_request_time))} seconds.'
                        }), 429
                    _rate_limit_storage[key] = (requests + 1, first_request_time)
            else:
                _rate_limit_storage[key] = (1, now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def cleanup_rate_limit_storage():
    """Remove old entries from rate limit storage"""
    current_time = time.time()
    keys_to_remove = []
    
    for key, (requests, first_request_time) in _rate_limit_storage.items():
        # Remove entries older than 1 hour
        if current_time - first_request_time > 3600:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        _rate_limit_storage.pop(key, None)


def detect_bot():
    """Detect if request is from a bot/scraper"""
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Allow if no user agent (might be legitimate API calls)
    if not user_agent:
        return False
    
    # Check for known legitimate browsers first
    legitimate_browsers = [
        'mozilla', 'chrome', 'safari', 'firefox', 'edge', 'opera',
        'webkit', 'gecko', 'msie', 'trident'
    ]
    
    # If it looks like a browser, allow it
    if any(browser in user_agent for browser in legitimate_browsers):
        return False
    
    # Check for suspicious user agents (only obvious bots)
    obvious_bots = [
        'bot/', 'crawler', 'spider', 'scraper', 
        'curl/', 'wget/', 'python-requests', 'scrapy',
        'go-http-client', 'apache-httpclient', 'okhttp'
    ]
    
    for pattern in obvious_bots:
        if pattern in user_agent:
            return True
    
    # Check for common bot patterns (more strict)
    bot_patterns = [
        r'bot[/\s]',
        r'crawler[/\s]',
        r'spider[/\s]',
        r'scraper[/\s]',
        r'^curl\s',
        r'^wget\s',
        r'python-requests',
        r'go-http-client',
        r'httpclient[/\s]'
    ]
    
    for pattern in bot_patterns:
        if re.search(pattern, user_agent, re.IGNORECASE):
            return True
    
    return False


def require_human():
    """Decorator to require human users (block bots)"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if detect_bot():
                logging.warning(f"Bot detected: {request.remote_addr} - {request.headers.get('User-Agent')}")
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_file_upload(file, allowed_types=None):
    """
    Validate uploaded file for security
    
    Args:
        file: FileStorage object from Flask
        allowed_types: List of allowed file types (images, documents, archives)
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not file or not file.filename:
        return False, "No file provided"
    
    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    max_size = current_app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
    if file_size > max_size:
        return False, f"File size exceeds maximum allowed size of {max_size / (1024*1024):.1f}MB"
    
    # Get file extension
    filename = secure_filename(file.filename)
    file_ext = os.path.splitext(filename)[1].lower()
    
    # Check allowed extensions
    if allowed_types:
        allowed_exts = set()
        for file_type in allowed_types:
            allowed_exts.update(ALLOWED_EXTENSIONS.get(file_type, set()))
        
        if file_ext not in allowed_exts:
            return False, f"File type not allowed. Allowed types: {', '.join(allowed_types)}"
    else:
        # Default: allow all known safe types
        all_allowed = set()
        for ext_set in ALLOWED_EXTENSIONS.values():
            all_allowed.update(ext_set)
        
        if file_ext not in all_allowed:
            return False, f"File extension '{file_ext}' is not allowed"
    
    # Check MIME type
    mime_type = file.content_type
    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        # Allow if extension is valid (some browsers send wrong MIME types)
        if file_ext in ['.jpg', '.jpeg'] and 'image' in mime_type:
            pass  # Allow
        elif file_ext in ['.xlsx'] and 'spreadsheet' in mime_type or 'excel' in mime_type:
            pass  # Allow
        elif file_ext in ['.docx'] and 'word' in mime_type or 'document' in mime_type:
            pass  # Allow
        else:
            logging.warning(f"Suspicious MIME type: {mime_type} for file {filename}")
            # Don't reject, but log for monitoring
    
    # Check for dangerous file names
    dangerous_patterns = [
        r'\.\.',  # Path traversal
        r'/',     # Directory separator
        r'\\',    # Windows directory separator
        r'%00',   # Null byte
        r'<',     # HTML injection
        r'>',
        r'&',
        r'"',
        r"'",
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, filename):
            return False, "Invalid characters in filename"
    
    return True, None


def sanitize_input(text, max_length=None):
    """
    Sanitize user input to prevent XSS
    
    Args:
        text: Input string
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    """
    if not text:
        return ""
    
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Remove control characters (except newlines and tabs)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    
    return text


def validate_sql_input(value, max_length=1000):
    """
    Validate input for SQL queries (additional layer of protection)
    Note: SQLAlchemy already provides protection, but this adds extra validation
    """
    if not value:
        return True, None
    
    if max_length and len(str(value)) > max_length:
        return False, f"Input exceeds maximum length of {max_length} characters"
    
    # Check for SQL injection patterns
    dangerous_patterns = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b)',
        r'(\b(OR|AND)\s+\d+\s*=\s*\d+)',
        r'(\'|\"|;|--|\/\*|\*\/)',
        r'(\bxp_\w+)',  # SQL Server extended procedures
        r'(\bsp_\w+)',  # SQL Server stored procedures
    ]
    
    value_str = str(value).upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, value_str, re.IGNORECASE):
            logging.warning(f"Potential SQL injection attempt detected: {value[:100]}")
            return False, "Invalid input detected"
    
    return True, None


def check_secret_key():
    """Verify that SECRET_KEY is properly configured"""
    secret_key = current_app.config.get('SECRET_KEY')
    
    if not secret_key or secret_key in ['your-secret-key-here', 'dev-secret-key', 'change-me']:
        logging.error("⚠️  SECURITY WARNING: SECRET_KEY is using default value!")
        logging.error("⚠️  Please set a strong SECRET_KEY in your environment variables")
        return False
    
    if len(secret_key) < 32:
        logging.warning("⚠️  SECURITY WARNING: SECRET_KEY is too short (minimum 32 characters recommended)")
        return False
    
    return True


def setup_security_middleware(app):
    """Setup all security middleware"""
    # Security headers
    setup_security_headers(app)
    
    # Check secret key on startup
    with app.app_context():
        if not check_secret_key():
            if app.config.get('ENV') == 'production':
                raise ValueError("SECRET_KEY must be set in production!")
    
    # Bot detection for sensitive endpoints
    @app.before_request
    def check_bot_for_sensitive_routes():
        """Block bots from sensitive routes"""
        # Skip bot detection for static files and robots.txt
        if request.path.startswith('/static') or request.path == '/robots.txt':
            return
        
        # Skip bot detection for authenticated users (they've already passed login)
        from flask_login import current_user
        if current_user.is_authenticated:
            return
        
        sensitive_paths = [
            '/dashboard',
            '/api',
            '/auth/login',
            '/auth/logout'
        ]
        
        if any(request.path.startswith(path) for path in sensitive_paths):
            if detect_bot():
                # Allow if it's an API call with proper authentication
                if request.path.startswith('/api'):
                    # Check for API key or authentication
                    api_key = request.headers.get('X-API-Key')
                    if not api_key:
                        logging.warning(f"Bot attempting to access API: {request.remote_addr} - {request.headers.get('User-Agent')}")
                        abort(403)
                else:
                    # For login/logout, allow bots to access (they need to login)
                    if request.path in ['/auth/login', '/auth/logout']:
                        return
                    logging.warning(f"Bot attempting to access sensitive route: {request.path}")
                    abort(403)
    
    # Request size limiting
    @app.before_request
    def check_request_size():
        """Check request size"""
        if request.content_length:
            max_size = current_app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
            if request.content_length > max_size:
                abort(413)  # Request Entity Too Large
    
    logging.info("✅ Security middleware initialized")


def generate_secure_filename(original_filename):
    """Generate a secure filename with timestamp and hash"""
    # Get secure base name
    base_name = secure_filename(original_filename)
    name, ext = os.path.splitext(base_name)
    
    # Add timestamp
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    # Add hash for uniqueness
    hash_suffix = hashlib.md5(f"{timestamp}{name}".encode()).hexdigest()[:8]
    
    return f"{timestamp}_{hash_suffix}{ext}"

