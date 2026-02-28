from flask import Flask, request
from app.config import config_map
from app.extensions import db, migrate, jwt
import os


def create_app(env: str = None) -> Flask:
    app = Flask(__name__)

    env = env or os.getenv("FLASK_ENV", "development")
    app.config.from_object(config_map.get(env, config_map["default"]))

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    allowed_origins = {
        item.strip()
        for item in app.config.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    }

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if not origin:
            return response

        if "*" in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        else:
            return response

        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response

    with app.app_context():
        # Import models so Flask-Migrate can detect them
        from app.db.models import User, Document, DocumentIngestion, Chunk  # noqa: F401

        # Register blueprints
        from app.api.auth import auth_bp
        from app.api.dev import dev_bp
        app.register_blueprint(auth_bp)
        app.register_blueprint(dev_bp)

    return app
