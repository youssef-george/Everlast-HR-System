from app import app  # noqa: F401
from flask import redirect, url_for

# Root route to redirect to login page
@app.route('/')
def index():
    return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
