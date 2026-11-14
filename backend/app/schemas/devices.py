"""Pydantic schemas for device-management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


Latitude = Annotated[float, Field(ge=-90, le=90, description="Latitude in decimal degrees.")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="Longitude in decimal degrees.")]


class SchemaBase(BaseModel):
    """Base schema with API-friendly validation and ORM serialization."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class DeviceCreateBase(SchemaBase):
    """Fields shared by device-creation requests."""

    device_id: str = Field(min_length=1, max_length=50, description="Globally unique device identifier.")
    location_name: str = Field(min_length=1, max_length=120)
    latitude: Latitude
    longitude: Longitude
    is_active: bool = True


class DeviceUpdateBase(SchemaBase):
    """Mutable device fields; device identifiers are intentionally immutable."""

    location_name: str = Field(min_length=1, max_length=120)
    latitude: Latitude
    longitude: Longitude
    is_active: bool


class DeviceStatusUpdate(SchemaBase):
    """Activation state for a device without changing its master record."""

    is_active: bool = Field(description="Set to false to deactivate without deleting history.")


class WaterTankCreate(DeviceCreateBase):
    """Request body for registering a water tank."""

    tank_name: str = Field(min_length=1, max_length=120)


class WaterTankUpdate(DeviceUpdateBase):
    """Full mutable state for a water tank."""

    tank_name: str = Field(min_length=1, max_length=120)


class WaterTankResponse(WaterTankCreate):
    """Water-tank data returned by the API."""

    tank_id: int
    created_at: datetime


class WasteBinCreate(DeviceCreateBase):
    """Request body for registering a waste bin."""

    bin_name: str = Field(min_length=1, max_length=120)


class WasteBinUpdate(DeviceUpdateBase):
    """Full mutable state for a waste bin."""

    bin_name: str = Field(min_length=1, max_length=120)


class WasteBinResponse(WasteBinCreate):
    """Waste-bin data returned by the API."""

    bin_id: int
    created_at: datetime


class AQIStationCreate(DeviceCreateBase):
    """Request body for registering an AQI station."""

    station_name: str = Field(min_length=1, max_length=120)


class AQIStationUpdate(DeviceUpdateBase):
    """Full mutable state for an AQI station."""

    station_name: str = Field(min_length=1, max_length=120)


class AQIStationResponse(AQIStationCreate):
    """AQI-station data returned by the API."""

    station_id: int
    created_at: datetime


class DeviceTypeSummary(SchemaBase):
    """Total and active count for one device type."""

    total: int = Field(ge=0)
    active: int = Field(ge=0)


class DevicesSummaryResponse(SchemaBase):
    """Inventory summary grouped by device type."""

    water_tanks: DeviceTypeSummary
    waste_bins: DeviceTypeSummary
    aqi_stations: DeviceTypeSummary
