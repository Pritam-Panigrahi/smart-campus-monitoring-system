"""Master-device and reading models for water, waste, and air quality."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SqlEnum, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for ORM-created records."""
    return datetime.now(timezone.utc)


class ReadingSource(str, Enum):
    """The permitted origins for a monitoring reading."""

    SIMULATED = "SIMULATED"
    CSV_UPLOAD = "CSV_UPLOAD"
    SENSOR = "SENSOR"


class WaterTank(Base):
    """A physical campus water tank registered for monitoring."""

    __tablename__ = "water_tanks"

    tank_id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    tank_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    readings: Mapped[list[WaterTankReading]] = relationship(back_populates="tank")


class WaterTankReading(Base):
    """A recorded water-level reading for a water tank."""

    __tablename__ = "water_tank_readings"
    __table_args__ = (
        CheckConstraint("water_percentage >= 0 AND water_percentage <= 100", name="ck_water_tank_readings_percentage"),
        Index("ix_water_tank_readings_tank_id_recorded_at", "tank_id", "recorded_at"),
    )

    reading_id: Mapped[int] = mapped_column(primary_key=True)
    tank_id: Mapped[int] = mapped_column(ForeignKey("water_tanks.tank_id", ondelete="RESTRICT"), nullable=False)
    water_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[ReadingSource] = mapped_column(
        SqlEnum(ReadingSource, name="reading_source", native_enum=False, create_constraint=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    tank: Mapped[WaterTank] = relationship(back_populates="readings")


class WasteBin(Base):
    """A physical campus waste bin registered for monitoring."""

    __tablename__ = "waste_bins"

    bin_id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    bin_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    readings: Mapped[list[WasteBinReading]] = relationship(back_populates="bin")


class WasteBinReading(Base):
    """A recorded fill-level reading for a waste bin."""

    __tablename__ = "waste_bin_readings"
    __table_args__ = (
        CheckConstraint("fill_percentage >= 0 AND fill_percentage <= 100", name="ck_waste_bin_readings_percentage"),
        Index("ix_waste_bin_readings_bin_id_recorded_at", "bin_id", "recorded_at"),
    )

    reading_id: Mapped[int] = mapped_column(primary_key=True)
    bin_id: Mapped[int] = mapped_column(ForeignKey("waste_bins.bin_id", ondelete="RESTRICT"), nullable=False)
    fill_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[ReadingSource] = mapped_column(
        SqlEnum(ReadingSource, name="reading_source", native_enum=False, create_constraint=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    bin: Mapped[WasteBin] = relationship(back_populates="readings")


class AQIStation(Base):
    """A physical campus station registered for air-quality monitoring."""

    __tablename__ = "aqi_stations"

    station_id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    readings: Mapped[list[AQIReading]] = relationship(back_populates="station")


class AQIReading(Base):
    """A recorded air-quality reading for an AQI station."""

    __tablename__ = "aqi_readings"
    __table_args__ = (
        CheckConstraint("current_aqi >= 0 AND current_aqi <= 500", name="ck_aqi_readings_value"),
        Index("ix_aqi_readings_station_id_recorded_at", "station_id", "recorded_at"),
    )

    reading_id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("aqi_stations.station_id", ondelete="RESTRICT"), nullable=False)
    current_aqi: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[ReadingSource] = mapped_column(
        SqlEnum(ReadingSource, name="reading_source", native_enum=False, create_constraint=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    station: Mapped[AQIStation] = relationship(back_populates="readings")
