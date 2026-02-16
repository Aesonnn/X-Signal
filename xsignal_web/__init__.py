from flask import Flask

from .dash_app import init_dashboard
from .routes import main_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(main_bp)
    init_dashboard(app)
    return app
