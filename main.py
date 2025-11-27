from app import create_app

app = create_app()
from flask import redirect, url_for, render_template, flash
from flask_wtf.csrf import CSRFError
from forms import LoginForm
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Root route to redirect to login page
@app.route('/')
def index():
    return redirect(url_for('auth.login'))

# Register error handlers after all imports
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logging.error(f"CSRF error: {str(e)}")
    flash('Session expired. Please try logging in again.', 'danger')
    return render_template('auth/login.html', form=LoginForm(), title='Login'), 400

if __name__ == '__main__':
    # Run the application on specific IP and port
    logging.info('Starting Everlast HR System on http://192.168.11.68:5000')
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False  # Set to False for production
    )
