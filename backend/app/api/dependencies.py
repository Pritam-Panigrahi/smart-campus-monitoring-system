"""Reusable FastAPI dependencies."""

from collections.abc import Generator

from app.core.database import SessionLocal


def get_db() -> Generator:
    """Yield a database session and always close it after the request."""
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
