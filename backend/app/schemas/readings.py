"""Pydantic schemas for monitoring-reading and dashboard endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import Field, field_validator

from app.models import ReadingSource
from app.schemas.devices import SchemaBase


class ReadingCreateBase(SchemaBase):
    """Fields common to all incoming monitoring readings."""

    source: ReadingSource = Field(description="Origin of the reading.")
    recorded_at: datetime | None = Field(
        default=None,
        description="Timezone-aware timestamp. Omit to use the current UTC time.",
    )

    @field_validator("recorded_at")
    @classmethod
    def normalise_recorded_at(cls, value: datetime | None) -> datetime | None:
        """Reject ambiguous timestamps and normalize accepted values to UTC."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone offset.")
        return value.astimezone(timezone.utc)


class ReadingResponseBase(SchemaBase):
    """Fields common to all reading responses."""

    reading_id: int
    source: ReadingSource
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def serialize_recorded_at_as_utc(cls, value: datetime) -> datetime:
        """Present SQLite's timezone-less values explicitly as UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class WaterTankReadingCreate(ReadingCreateBase):
    """Payload for a water-tank level reading."""

    water_percentage: float = Field(ge=0, le=100)


class WaterTankReadingResponse(ReadingResponseBase):
    """Water-tank reading returned by the API."""

    tank_id: int
    water_percentage: float


class WasteBinReadingCreate(ReadingCreateBase):
    """Payload for a waste-bin fill reading."""

    fill_percentage: float = Field(ge=0, le=100)


class WasteBinReadingResponse(ReadingResponseBase):
    """Waste-bin reading returned by the API."""

    bin_id: int
    fill_percentage: float


class AQIReadingCreate(ReadingCreateBase):
    """Payload for an air-quality reading."""

    current_aqi: int = Field(ge=0, le=500)


class AQIReadingResponse(ReadingResponseBase):
    """AQI reading returned by the API."""

    station_id: int
    current_aqi: int


class WaterTankDashboardDevice(SchemaBase):
    """Dashboard state for one water tank."""

    device_id: str
    tank_name: str
    location_name: str
    is_active: bool
    status: str
    latest_reading: WaterTankReadingResponse | None


class WasteBinDashboardDevice(SchemaBase):
    """Dashboard state for one waste bin."""

    device_id: str
    bin_name: str
    location_name: str
    is_active: bool
    status: str
    latest_reading: WasteBinReadingResponse | None


class AQIStationDashboardDevice(SchemaBase):
    """Dashboard state for one AQI station."""

    device_id: str
    station_name: str
    location_name: str
    is_active: bool
    status: str
    latest_reading: AQIReadingResponse | None


class DashboardSummaryResponse(SchemaBase):
    """Current inventory, latest readings, statuses, and active alerts."""

    total_water_tanks: int
    active_water_tanks: int
    total_waste_bins: int
    active_waste_bins: int
    total_aqi_stations: int
    active_aqi_stations: int
    active_alert_count: int
    water_tanks: list[WaterTankDashboardDevice]
    waste_bins: list[WasteBinDashboardDevice]
    aqi_stations: list[AQIStationDashboardDevice]
