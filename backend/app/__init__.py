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

    def _cors_origin(origin: str) -> str | None:
        if "*" in allowed_origins:
            return "*"
        if origin in allowed_origins:
            return origin
        return None

    @app.before_request
    def handle_options_preflight():
        """Return 200 immediately for all OPTIONS preflight requests with CORS headers."""
        if request.method != "OPTIONS":
            return None
        origin = request.headers.get("Origin", "")
        allowed = _cors_origin(origin)
        if not allowed:
            return None  # not an allowed origin, fall through to 405
        from flask import make_response
        resp = make_response("", 200)
        resp.headers["Access-Control-Allow-Origin"] = allowed
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "86400"
        if allowed != "*":
            resp.headers["Vary"] = "Origin"
        return resp

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin", "")
        if not origin:
            return response
        allowed = _cors_origin(origin)
        if not allowed:
            return response
        response.headers["Access-Control-Allow-Origin"] = allowed
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        if allowed != "*":
            response.headers["Vary"] = "Origin"
        return response

    with app.app_context():
        # Import models so Flask-Migrate can detect them
        from app.db.models import (
            User,
            Document,
            DocumentIngestion,
            Chunk,
            Chat,
            ChatMessage,
            ChatMessageSource,
            Quiz,
            QuizQuestion,
            QuizQuestionSource,
            QuizAttempt,
            QuizAttemptAnswer,
            Event,
        )  # noqa: F401

        # Register blueprints
        from app.api.auth import auth_bp
        from app.api.dev import dev_bp
        from app.api.documents import documents_bp
        from app.api.chat import chat_bp
        from app.api.quizzes import quizzes_bp
        from app.api.analytics import analytics_bp
        app.register_blueprint(auth_bp)
        app.register_blueprint(dev_bp)
        app.register_blueprint(documents_bp)
        app.register_blueprint(chat_bp)
        app.register_blueprint(quizzes_bp)
        app.register_blueprint(analytics_bp)

    return app
