import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")

    # LLM Wrapper
    WRAPPER_BASE_URL = os.getenv("WRAPPER_BASE_URL", "")
    WRAPPER_KEY = os.getenv("WRAPPER_KEY", "")

    # Browser frontend origins allowed to call backend APIs
    CORS_ALLOWED_ORIGINS = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://127.0.0.1:3000",
    )


class DevelopmentConfig(Config):
    DEBUG = True
    PROPAGATE_EXCEPTIONS = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
