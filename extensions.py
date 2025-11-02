# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_apscheduler import APScheduler

db = SQLAlchemy()
login_manager = LoginManager()
scheduler = APScheduler()
