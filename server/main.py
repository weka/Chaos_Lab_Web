from app import create_app
from flask_socketio import SocketIO
import terminal as terminal_module  # Ensure terminal.py is in the same folder as main.py

app = create_app()

# Use eventlet as async mode and allow all origins.
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

if __name__ == '__main__':
    # Run with eventlet; allow_unsafe_werkzeug is not necessary when using eventlet,
    # but you can include it if you want.
    socketio.run(app, host="0.0.0.0", port=5000)

