import logging
from flask import Flask, request
from flask_cors import CORS  # Import Flask-CORS for handling CORS
from app import create_app

# Configure Flask and Werkzeug logging
logging.basicConfig(level=logging.DEBUG)  # Set the root logger to DEBUG level
logger = logging.getLogger('werkzeug')  # Get the Werkzeug logger
logger.setLevel(logging.DEBUG)  # Set Werkzeug to DEBUG level as well

# Create Flask app
app = create_app()

# Enable CORS for all routes
CORS(app)  # Allow all origins by default

# Log incoming requests
@app.before_request
def log_request_info():
    app.logger.debug(f"Incoming request: {request.method} {request.url}")
    app.logger.debug(f"Request headers: {request.headers}")
    app.logger.debug(f"Request body: {request.get_data()}")

# Log outgoing responses
@app.after_request
def log_response_info(response):
    app.logger.debug(f"Response status: {response.status}")
    app.logger.debug(f"Response headers: {response.headers}")
    return response

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

