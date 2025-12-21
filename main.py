"""
Main entry point for the Flask application
Used for running the app directly with Python
"""
import os
import sys
import logging
import traceback

# Configure logging FIRST before any other imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

try:
    from flask import redirect, url_for, render_template, flash
    from flask_wtf.csrf import CSRFError
    from forms import LoginForm
    from app import create_app
    
    logger.info("Imports successful")
except Exception as e:
    logger.error(f"Failed to import modules: {str(e)}", exc_info=True)
    sys.exit(1)

# Determine config based on environment
config_name = 'production' if os.environ.get('FLASK_ENV') == 'production' else 'default'
logger.info(f"Using config: {config_name}")

# Create the Flask application
try:
    logger.info("Creating Flask app...")
    app = create_app(config_name=config_name)
    logger.info(f'Flask app created successfully with config: {config_name}')
except Exception as e:
    logger.error(f'Failed to create Flask app: {str(e)}', exc_info=True)
    traceback.print_exc()
    sys.exit(1)

# Health check endpoint for container orchestration
@app.route('/health')
def health_check():
    """Health check endpoint for container orchestration"""
    try:
        # Simple health check - just return OK
        return {'status': 'healthy', 'service': 'Everlast ERP'}, 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {'status': 'unhealthy', 'error': str(e)}, 500

# Root route to redirect to login page
@app.route('/')
def index():
    return redirect(url_for('auth.login'))

# Register error handlers
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.error(f"CSRF error: {str(e)}")
    flash('Session expired. Please try logging in again.', 'danger')
    return render_template('auth/login.html', form=LoginForm(), title='Login'), 400

if __name__ == '__main__':
    # Get host and port from environment variables (set by Coolify)
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    
    # Run the application
    logger.info('=' * 70)
    logger.info('Starting Everlast ERP')
    logger.info('=' * 70)
    logger.info(f'Host: {host}')
    logger.info(f'Port: {port}')
    logger.info(f'Environment: {os.environ.get("FLASK_ENV", "not set")}')
    logger.info(f'Database URI configured: {bool(app.config.get("SQLALCHEMY_DATABASE_URI"))}')
    logger.info('=' * 70)
    
    # Ensure the app stays running - don't exit on errors
    logger.info("Starting Flask development server...")
    logger.info(f"Server will be available at http://{host}:{port}")
    logger.info("Press CTRL+C to stop the server")
    
    try:
        # Start the Flask server
        logger.info("=" * 70)
        logger.info("🚀 Flask server starting...")
        logger.info("=" * 70)
        app.run(
            host=host,
            port=port,
            debug=False,  # Set to False for production
            use_reloader=False,  # Disable reloader in production
            threaded=True  # Enable threading for better performance
        )
        logger.info("Flask server stopped")
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f'Failed to start Flask app: {str(e)}', exc_info=True)
        traceback.print_exc()
        # Don't exit immediately - wait a bit to see if it's a transient error
        import time
        logger.error("Waiting 5 seconds before exiting...")
        time.sleep(5)
        sys.exit(1)
