"""Shared persistence service for append-only monitoring readings."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AQIReading, ReadingSource, WasteBinReading, WaterTankReading
from app.services.dashboard import aqi_status, get_dashboard_summary, waste_status, water_status
from app.websockets.monitoring import connection_manager


logger = logging.getLogger(__name__)

READING_EVENTS: dict[type[Any], tuple[str, str, str, Any]] = {
    WaterTankReading: ("WATER_TANK_READING", "water_tanks", "water_percentage", water_status),
    WasteBinReading: ("WASTE_BIN_READING", "waste_bins", "fill_percentage", waste_status),
    AQIReading: ("AQI_READING", "aqi_stations", "current_aqi", aqi_status),
}


def append_reading(database: Session, device: Any, model: Any, parent_field: str, values: dict[str, Any]) -> Any:
    """Append and commit one reading while preserving all historical records."""
    device_id = device.device_id
    is_active = device.is_active
    reading = model(**{parent_field: getattr(device, parent_field)}, **values)
    database.add(reading)
    try:
        database.commit()
    except Exception:
        database.rollback()
        raise
    database.refresh(reading)
    _publish_reading_events(database, reading, device_id, is_active)
    return reading


def _publish_reading_events(database: Session, reading: Any, device_id: str, is_active: bool) -> None:
    """Publish a saved reading and current dashboard snapshot when clients are connected."""
    if connection_manager.client_count == 0:
        return

    try:
        event_name, module, value_field, status_for_value = READING_EVENTS[type(reading)]
        value = getattr(reading, value_field)
        status = status_for_value(value, is_active)
        recorded_at = reading.recorded_at
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        else:
            recorded_at = recorded_at.astimezone(timezone.utc)

        reading_event = {
            "event": event_name,
            "device_id": device_id,
            "module": module,
            "reading_id": reading.reading_id,
            "value": value,
            "status": status,
            "source": reading.source.value if isinstance(reading.source, ReadingSource) else reading.source,
            "recorded_at": recorded_at.isoformat(),
        }
        summary = get_dashboard_summary(database).model_dump(mode="json")
        connection_manager.publish(reading_event)
        connection_manager.publish({"event": "DASHBOARD_UPDATE", "summary": summary})
    except Exception:
        logger.exception("Reading %s was saved, but its live update could not be prepared.", reading.reading_id)
