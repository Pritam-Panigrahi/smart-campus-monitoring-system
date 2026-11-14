"""Dashboard summary construction shared by the API and live updates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import AQIReading, AQIStation, WasteBin, WasteBinReading, WaterTank, WaterTankReading
from app.schemas.readings import (
    AQIReadingResponse,
    AQIStationDashboardDevice,
    DashboardSummaryResponse,
    WasteBinDashboardDevice,
    WasteBinReadingResponse,
    WaterTankDashboardDevice,
    WaterTankReadingResponse,
)


def latest_readings_by_parent(database: Session, model: Any, parent_column: Any) -> dict[int, Any]:
    """Fetch the latest reading per parent in one indexed window-function query."""
    ranked = (
        select(
            model.reading_id,
            parent_column.label("parent_id"),
            func.row_number()
            .over(partition_by=parent_column, order_by=(desc(model.recorded_at), desc(model.reading_id)))
            .label("row_number"),
        )
        .subquery()
    )
    readings = database.scalars(
        select(model).join(ranked, model.reading_id == ranked.c.reading_id).where(ranked.c.row_number == 1)
    ).all()
    return {getattr(reading, parent_column.key): reading for reading in readings}


def water_status(value: float | None, is_active: bool) -> str:
    """Classify a water tank using the provisional dashboard thresholds."""
    if not is_active:
        return "Inactive"
    if value is None:
        return "No data"
    if value >= 50:
        return "Normal"
    if value >= 25:
        return "Attention"
    if value >= 10:
        return "Low"
    return "Critical"


def waste_status(value: float | None, is_active: bool) -> str:
    """Classify a waste bin using the provisional dashboard thresholds."""
    if not is_active:
        return "Inactive"
    if value is None:
        return "No data"
    if value <= 25:
        return "Low"
    if value <= 50:
        return "Medium"
    if value <= 80:
        return "Almost Full"
    return "Full"


def aqi_status(value: int | None, is_active: bool) -> str:
    """Classify an AQI station using the provisional dashboard thresholds."""
    if not is_active:
        return "Inactive"
    if value is None:
        return "No data"
    if value <= 50:
        return "Good"
    if value <= 100:
        return "Satisfactory"
    if value <= 200:
        return "Moderate"
    if value <= 300:
        return "Poor"
    if value <= 400:
        return "Very Poor"
    return "Severe"


def get_dashboard_summary(database: Session) -> DashboardSummaryResponse:
    """Return inventory, per-device current status, and latest data."""
    tanks = list(database.scalars(select(WaterTank).order_by(WaterTank.device_id)).all())
    bins = list(database.scalars(select(WasteBin).order_by(WasteBin.device_id)).all())
    stations = list(database.scalars(select(AQIStation).order_by(AQIStation.device_id)).all())
    tank_latest = latest_readings_by_parent(database, WaterTankReading, WaterTankReading.tank_id)
    bin_latest = latest_readings_by_parent(database, WasteBinReading, WasteBinReading.bin_id)
    station_latest = latest_readings_by_parent(database, AQIReading, AQIReading.station_id)

    water_devices = []
    waste_devices = []
    aqi_devices = []
    active_alert_count = 0

    for tank in tanks:
        reading = tank_latest.get(tank.tank_id) if tank.is_active else None
        value = reading.water_percentage if reading is not None else None
        if tank.is_active and value is not None and value < 25:
            active_alert_count += 1
        water_devices.append(
            WaterTankDashboardDevice(
                device_id=tank.device_id,
                tank_name=tank.tank_name,
                location_name=tank.location_name,
                is_active=tank.is_active,
                status=water_status(value, tank.is_active),
                latest_reading=WaterTankReadingResponse.model_validate(reading) if reading is not None else None,
            )
        )

    for waste_bin in bins:
        reading = bin_latest.get(waste_bin.bin_id) if waste_bin.is_active else None
        value = reading.fill_percentage if reading is not None else None
        if waste_bin.is_active and value is not None and value > 80:
            active_alert_count += 1
        waste_devices.append(
            WasteBinDashboardDevice(
                device_id=waste_bin.device_id,
                bin_name=waste_bin.bin_name,
                location_name=waste_bin.location_name,
                is_active=waste_bin.is_active,
                status=waste_status(value, waste_bin.is_active),
                latest_reading=WasteBinReadingResponse.model_validate(reading) if reading is not None else None,
            )
        )

    for station in stations:
        reading = station_latest.get(station.station_id) if station.is_active else None
        value = reading.current_aqi if reading is not None else None
        if station.is_active and value is not None and value > 200:
            active_alert_count += 1
        aqi_devices.append(
            AQIStationDashboardDevice(
                device_id=station.device_id,
                station_name=station.station_name,
                location_name=station.location_name,
                is_active=station.is_active,
                status=aqi_status(value, station.is_active),
                latest_reading=AQIReadingResponse.model_validate(reading) if reading is not None else None,
            )
        )

    return DashboardSummaryResponse(
        total_water_tanks=len(tanks),
        active_water_tanks=sum(tank.is_active for tank in tanks),
        total_waste_bins=len(bins),
        active_waste_bins=sum(waste_bin.is_active for waste_bin in bins),
        total_aqi_stations=len(stations),
        active_aqi_stations=sum(station.is_active for station in stations),
        active_alert_count=active_alert_count,
        water_tanks=water_devices,
        waste_bins=waste_devices,
        aqi_stations=aqi_devices,
    )
