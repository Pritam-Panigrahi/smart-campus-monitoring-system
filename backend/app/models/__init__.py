"""SQLAlchemy ORM models for the Smart Campus Monitoring System."""

from app.models.monitoring import (
    AQIReading,
    AQIStation,
    ReadingSource,
    WasteBin,
    WasteBinReading,
    WaterTank,
    WaterTankReading,
)

__all__ = [
    "AQIReading",
    "AQIStation",
    "ReadingSource",
    "WasteBin",
    "WasteBinReading",
    "WaterTank",
    "WaterTankReading",
]
