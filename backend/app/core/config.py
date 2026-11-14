"""Environment-backed application settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")


def _sqlite_url_at_project_root(database_url: str) -> str:
    """Resolve a relative SQLite database URL from the project root."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.startswith("sqlite:////"):
        return database_url

    database_path = database_url.removeprefix(prefix)
    if database_path == ":memory:" or Path(database_path).is_absolute():
        return database_url

    return f"sqlite:///{PROJECT_ROOT / database_path}"


def _normalise_database_url(database_url: str) -> str:
    """Use SQLAlchemy's Psycopg 3 dialect for Render/PostgreSQL URLs."""
    database_url = _sqlite_url_at_project_root(database_url)
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    if database_url.startswith("postgresql://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgresql://')}"
    return database_url


class Settings:
    """Immutable application settings loaded once at startup."""

    app_name: str
    app_env: str
    cors_origins: list[str]
    database_url: str
    simulation_default_mode: str

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "Smart Campus Monitoring System")
        self.app_env = os.getenv("APP_ENV", "development")
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        self.cors_origins = [origin.strip() for origin in origins.split(",") if origin.strip()]
        raw_database_url = os.getenv("DATABASE_URL", "sqlite:///smart_campus.db")
        self.database_url = _normalise_database_url(raw_database_url)
        self.simulation_default_mode = os.getenv("SIMULATION_DEFAULT_MODE", "DEMO").upper()


settings = Settings()
