from flask import Flask
from flask_socketio import SocketIO
from config import Config
import logging # For debugging
from flask_cors import CORS

# Initialize SocketIO but don't attach to app yet
socketio = SocketIO()

def create_app(config_class=Config):
    app = Flask(__name__, template_folder="../") # Assuming client is served separately
    app.config.from_object(config_class)
    app.logger.setLevel(logging.DEBUG) # Ensure app logger is set to debug
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    # Initialize Flask-SocketIO with the app
    # Use eventlet for async mode, good for websockets
    socketio.init_app(app, async_mode='eventlet', cors_allowed_origins="*")


    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # Import Socket.IO event handlers AFTER app and socketio are initialized
    # to avoid circular imports and ensure context is available.
    with app.app_context():
        from app.api import terminal_events # noqa

    @app.route('/')
    def index():
        return "Flask app is running! Use /api/scenarios for API endpoints and /socket.io for WebSockets."

    app.logger.info("Flask App created with SocketIO.")
    return app
