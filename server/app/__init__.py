from flask import Flask
from config import Config

def create_app(config_class=Config):
    app = Flask(__name__, template_folder="../")
    app.config.from_object(config_class)

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    @app.route('/')
    def index():
        return "Flask app is running! Use /api/scenarios for API endpoints."

    return app

