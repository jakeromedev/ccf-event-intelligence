"""Shared Flask extensions initialized by the application factory."""

from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect


login_manager = LoginManager()
csrf = CSRFProtect()
