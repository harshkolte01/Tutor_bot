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

    # Embedding wrapper
    WRAPPER_BASE_URL = os.getenv("WRAPPER_BASE_URL", "")
    WRAPPER_KEY = os.getenv("WRAPPER_KEY", "")
    WRAPPER_TIMEOUT = int(os.getenv("WRAPPER_TIMEOUT", "120"))      # seconds
    WRAPPER_MAX_RETRIES = int(os.getenv("WRAPPER_MAX_RETRIES", "3"))
    WRAPPER_BASE_DELAY = float(os.getenv("WRAPPER_BASE_DELAY", "1.0"))  # seconds
    WRAPPER_EMBEDDING_MODEL = os.getenv("WRAPPER_EMBEDDING_MODEL", "gemini/gemini-embedding-001")

    # Ollama generation
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:0.8b")
    OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "")
    OLLAMA_REASONING_EFFORT = os.getenv("OLLAMA_REASONING_EFFORT", "none")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))      # seconds
    OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
    OLLAMA_BASE_DELAY = float(os.getenv("OLLAMA_BASE_DELAY", "0.5"))  # seconds

    # Legacy alias kept for older code paths and environment files.
    WRAPPER_DEFAULT_MODEL = os.getenv("WRAPPER_DEFAULT_MODEL", OLLAMA_MODEL)

    # File uploads
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "")  # default: instance/uploads

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
