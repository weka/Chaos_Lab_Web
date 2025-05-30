from flask import Blueprint

bp = Blueprint('api', __name__)

# Import routes and SocketIO events
from app.api import scenarios
# terminal_events will be imported in app/__init__.py after socketio is initialized
# from app.api import terminal_events
