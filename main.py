from app import app  # noqa: F401
from flask import redirect, url_for, render_template, flash
from flask_wtf.csrf import CSRFError
from forms import LoginForm
import logging

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
    app.run(host='0.0.0.0', port=5000, debug=True)
