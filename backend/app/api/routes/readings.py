"""Monitoring-reading routes for water tanks, waste bins, and AQI stations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.routes.devices import get_device_or_404
from app.models import AQIReading, AQIStation, WasteBin, WasteBinReading, WaterTank, WaterTankReading
from app.schemas.readings import (
    AQIReadingCreate,
    AQIReadingResponse,
    WasteBinReadingCreate,
    WasteBinReadingResponse,
    WaterTankReadingCreate,
    WaterTankReadingResponse,
)
from app.services.readings import append_reading


router = APIRouter(tags=["Monitoring readings"])


def normalise_query_timestamp(value: datetime | None, field_name: str) -> datetime | None:
    """Ensure optional date filters are timezone-aware UTC timestamps."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must include a timezone offset.")
    return value.astimezone(timezone.utc)


def filtered_readings_query(
    model: Any,
    parent_column: Any,
    parent_id: int,
    start_date: datetime | None,
    end_date: datetime | None,
) -> Select[Any]:
    """Build a date-filtered query ordered newest-first with stable ties."""
    statement = select(model).where(parent_column == parent_id)
    if start_date is not None:
        statement = statement.where(model.recorded_at >= start_date)
    if end_date is not None:
        statement = statement.where(model.recorded_at <= end_date)
    return statement.order_by(desc(model.recorded_at), desc(model.reading_id))


def list_readings(
    database: Session,
    model: Any,
    parent_column: Any,
    parent_id: int,
    limit: int,
    offset: int,
    start_date: datetime | None,
    end_date: datetime | None,
) -> list[Any]:
    """Execute a filtered, paginated reading query."""
    start = normalise_query_timestamp(start_date, "start_date")
    end = normalise_query_timestamp(end_date, "end_date")
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be earlier than or equal to end_date.")
    statement = filtered_readings_query(model, parent_column, parent_id, start, end)
    return list(database.scalars(statement.limit(limit).offset(offset)).all())


def latest_reading(database: Session, model: Any, parent_column: Any, parent_id: int) -> Any:
    """Return the most recently recorded reading, or 404 when none exists."""
    reading = database.scalar(
        select(model)
        .where(parent_column == parent_id)
        .order_by(desc(model.recorded_at), desc(model.reading_id))
        .limit(1)
    )
    if reading is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No readings found for this device.")
    return reading


def create_reading(database: Session, device: Any, model: Any, parent_field: str, payload: Any) -> Any:
    """Append a reading only when its parent device remains active."""
    if not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot add a reading to an inactive device. Activate it first.",
        )
    return append_reading(database, device, model, parent_field, payload.model_dump(exclude_none=True))


@router.post("/water-tanks/{device_id}/readings", response_model=WaterTankReadingResponse, status_code=status.HTTP_201_CREATED, summary="Add a water-tank reading")
def add_water_tank_reading(device_id: str, payload: WaterTankReadingCreate, database: Session = Depends(get_db)) -> WaterTankReading:
    """Append a validated water-level reading for an active tank."""
    tank = get_device_or_404(database, WaterTank, device_id, "Water tank")
    return create_reading(database, tank, WaterTankReading, "tank_id", payload)


@router.get("/water-tanks/{device_id}/readings", response_model=list[WaterTankReadingResponse], summary="List water-tank readings")
def get_water_tank_readings(
    device_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    database: Session = Depends(get_db),
) -> list[WaterTankReading]:
    """List tank history newest-first, optionally filtered by an inclusive UTC range."""
    tank = get_device_or_404(database, WaterTank, device_id, "Water tank")
    return list_readings(database, WaterTankReading, WaterTankReading.tank_id, tank.tank_id, limit, offset, start_date, end_date)


@router.get("/water-tanks/{device_id}/readings/latest", response_model=WaterTankReadingResponse, summary="Get latest water-tank reading")
def get_latest_water_tank_reading(device_id: str, database: Session = Depends(get_db)) -> WaterTankReading:
    """Get the newest recorded water-level reading for a tank."""
    tank = get_device_or_404(database, WaterTank, device_id, "Water tank")
    return latest_reading(database, WaterTankReading, WaterTankReading.tank_id, tank.tank_id)


@router.post("/waste-bins/{device_id}/readings", response_model=WasteBinReadingResponse, status_code=status.HTTP_201_CREATED, summary="Add a waste-bin reading")
def add_waste_bin_reading(device_id: str, payload: WasteBinReadingCreate, database: Session = Depends(get_db)) -> WasteBinReading:
    """Append a validated fill-level reading for an active bin."""
    waste_bin = get_device_or_404(database, WasteBin, device_id, "Waste bin")
    return create_reading(database, waste_bin, WasteBinReading, "bin_id", payload)


@router.get("/waste-bins/{device_id}/readings", response_model=list[WasteBinReadingResponse], summary="List waste-bin readings")
def get_waste_bin_readings(
    device_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    database: Session = Depends(get_db),
) -> list[WasteBinReading]:
    """List bin history newest-first, optionally filtered by an inclusive UTC range."""
    waste_bin = get_device_or_404(database, WasteBin, device_id, "Waste bin")
    return list_readings(database, WasteBinReading, WasteBinReading.bin_id, waste_bin.bin_id, limit, offset, start_date, end_date)


@router.get("/waste-bins/{device_id}/readings/latest", response_model=WasteBinReadingResponse, summary="Get latest waste-bin reading")
def get_latest_waste_bin_reading(device_id: str, database: Session = Depends(get_db)) -> WasteBinReading:
    """Get the newest recorded fill-level reading for a bin."""
    waste_bin = get_device_or_404(database, WasteBin, device_id, "Waste bin")
    return latest_reading(database, WasteBinReading, WasteBinReading.bin_id, waste_bin.bin_id)


@router.post("/aqi-stations/{device_id}/readings", response_model=AQIReadingResponse, status_code=status.HTTP_201_CREATED, summary="Add an AQI reading")
def add_aqi_reading(device_id: str, payload: AQIReadingCreate, database: Session = Depends(get_db)) -> AQIReading:
    """Append a validated AQI reading for an active station."""
    station = get_device_or_404(database, AQIStation, device_id, "AQI station")
    return create_reading(database, station, AQIReading, "station_id", payload)


@router.get("/aqi-stations/{device_id}/readings", response_model=list[AQIReadingResponse], summary="List AQI readings")
def get_aqi_readings(
    device_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    database: Session = Depends(get_db),
) -> list[AQIReading]:
    """List station history newest-first, optionally filtered by an inclusive UTC range."""
    station = get_device_or_404(database, AQIStation, device_id, "AQI station")
    return list_readings(database, AQIReading, AQIReading.station_id, station.station_id, limit, offset, start_date, end_date)


@router.get("/aqi-stations/{device_id}/readings/latest", response_model=AQIReadingResponse, summary="Get latest AQI reading")
def get_latest_aqi_reading(device_id: str, database: Session = Depends(get_db)) -> AQIReading:
    """Get the newest recorded AQI reading for a station."""
    station = get_device_or_404(database, AQIStation, device_id, "AQI station")
    return latest_reading(database, AQIReading, AQIReading.station_id, station.station_id)
