from flask import Flask
from flask_cors import CORS
import terminal as terminal_module

def create_app():
    app = Flask(__name__)
    # Enable CORS on all routes under /api/*
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # ... your other app setup code, for example registering blueprints
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app

