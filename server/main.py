import logging
from flask import Flask, request
# from flask_cors import CORS # No longer needed here if done in create_app
from app import create_app, socketio
import eventlet

eventlet.monkey_patch()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('werkzeug')
logger.setLevel(logging.DEBUG)
app_logger = logging.getLogger('flask.app')
app_logger.setLevel(logging.DEBUG)

app = create_app()

@app.before_request
def log_request_info():
    app.logger.debug(f"Incoming HTTP request: {request.method} {request.url}")
    app.logger.debug(f"Request headers: {request.headers}")
    if request.data:
        app.logger.debug(f"Request body: {request.get_data(as_text=True)}")

@app.after_request
def log_response_info(response):
    # Ensure CORS headers are present on *all* responses from /api/*
    # This is a bit redundant if CORS(app, resources={r"/api/*": ...}) is working,
    # but can be a useful debugging step or forceful addition.
    if request.path.startswith('/api/'):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
    app.logger.debug(f"Response status: {response.status}")
    app.logger.debug(f"Response headers: {response.headers}")
    return response

if __name__ == '__main__':
    app.logger.info("Starting Flask-SocketIO server...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=True)
