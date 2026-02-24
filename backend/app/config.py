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
    WRAPPER_TIMEOUT = int(os.getenv("WRAPPER_TIMEOUT", "30"))      # seconds
    WRAPPER_MAX_RETRIES = int(os.getenv("WRAPPER_MAX_RETRIES", "3"))
    WRAPPER_BASE_DELAY = float(os.getenv("WRAPPER_BASE_DELAY", "1.0"))  # seconds
    # Default model routing (services can override per call)
    WRAPPER_DEFAULT_MODEL = os.getenv("WRAPPER_DEFAULT_MODEL", "routeway/glm-4.5-air:free")
    WRAPPER_EMBEDDING_MODEL = os.getenv("WRAPPER_EMBEDDING_MODEL", "gemini/gemini-embedding-001")

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
