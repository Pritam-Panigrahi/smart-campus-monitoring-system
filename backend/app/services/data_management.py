"""Shared CSV validation, persistence metadata, and live-update publishing."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AQIReading, AQIStation, ReadingSource, WasteBin, WasteBinReading, WaterTank, WaterTankReading
from app.services.dashboard import aqi_status, get_dashboard_summary, waste_status, water_status
from app.websockets.monitoring import connection_manager

MAX_CSV_SIZE = 5 * 1024 * 1024


@dataclass(frozen=True)
class ModuleConfig:
    model: Any
    reading_model: Any
    parent_field: str
    value_field: str
    value_label: str
    maximum: int
    event: str
    status_for_value: Any
    name_field: str


MODULES: dict[str, ModuleConfig] = {
    "water_tanks": ModuleConfig(WaterTank, WaterTankReading, "tank_id", "water_percentage", "water_percentage", 100, "WATER_TANK_READING", water_status, "tank_name"),
    "waste_bins": ModuleConfig(WasteBin, WasteBinReading, "bin_id", "fill_percentage", "fill_percentage", 100, "WASTE_BIN_READING", waste_status, "bin_name"),
    "aqi_stations": ModuleConfig(AQIStation, AQIReading, "station_id", "current_aqi", "current_aqi", 500, "AQI_READING", aqi_status, "station_name"),
}


def module_config(module: str) -> ModuleConfig:
    """Resolve only explicitly supported modules."""
    config = MODULES.get(module)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported module. Use water_tanks, waste_bins, or aqi_stations.")
    return config


def parse_csv(content: bytes, config: ModuleConfig, database: Session) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Parse every row before persistence so imports cannot be partial."""
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The CSV file is empty.")
    if len(content) > MAX_CSV_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV files may not exceed 5 MB.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSV must be UTF-8 encoded.") from error
    try:
        reader = csv.DictReader(io.StringIO(decoded))
        required = {"device_id", config.value_field, "recorded_at"}
        headers = set(reader.fieldnames or [])
        missing = sorted(required - headers)
        if missing:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"CSV is missing required columns: {', '.join(missing)}.")
        unknown_source = "source" in headers
        devices = {device.device_id: device for device in database.scalars(select(config.model)).all()}
        valid: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        total = 0
        for row_number, row in enumerate(reader, start=2):
            total += 1
            messages: list[str] = []
            device_id = (row.get("device_id") or "").strip()
            if not device_id:
                messages.append("device_id is required")
            elif device_id not in devices:
                messages.append(f"device_id '{device_id}' does not belong to this module")
            raw_value = (row.get(config.value_field) or "").strip()
            try:
                value = float(raw_value)
                if value < 0 or value > config.maximum:
                    messages.append(f"{config.value_field} must be between 0 and {config.maximum}")
                if config.value_field == "current_aqi" and not value.is_integer():
                    messages.append("current_aqi must be a whole number")
            except ValueError:
                value = None
                messages.append(f"{config.value_field} must be numeric")
            raw_timestamp = (row.get("recorded_at") or "").strip()
            try:
                recorded_at = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
                    messages.append("recorded_at must include a timezone offset")
                else:
                    recorded_at = recorded_at.astimezone(timezone.utc)
            except ValueError:
                recorded_at = None
                messages.append("recorded_at must be an ISO-8601 timestamp")
            if unknown_source and (row.get("source") or "").strip():
                try:
                    ReadingSource((row.get("source") or "").strip())
                except ValueError:
                    messages.append("source must be SIMULATED, SENSOR, or CSV_UPLOAD when provided")
            if messages:
                errors.append({"row": row_number, "reason": "; ".join(messages)})
            else:
                valid.append({"device": devices[device_id], "device_id": device_id, "value": int(value) if config.value_field == "current_aqi" else value, "recorded_at": recorded_at})
    except csv.Error as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Malformed CSV file.") from error
    return valid, errors, total


def add_readings(database: Session, config: ModuleConfig, records: list[dict[str, Any]], replace: bool) -> list[tuple[Any, Any]]:
    """Atomically add a complete validated set, optionally replacing one module."""
    try:
        if replace:
            database.execute(delete(config.reading_model))
        created: list[tuple[Any, Any]] = []
        for record in records:
            reading = config.reading_model(**{config.parent_field: getattr(record["device"], config.parent_field), config.value_field: record["value"], "source": ReadingSource.CSV_UPLOAD, "recorded_at": record["recorded_at"]})
            database.add(reading)
            created.append((reading, record["device"]))
        database.commit()
        for reading, _device in created:
            database.refresh(reading)
        return created
    except Exception:
        database.rollback()
        raise


def publish_import(database: Session, module: str, config: ModuleConfig, created: list[tuple[Any, Any]]) -> None:
    """Publish the newest imported reading per device only after commit, plus one summary."""
    if connection_manager.client_count == 0:
        return
    newest: dict[str, tuple[Any, Any]] = {}
    for reading, device in created:
        prior = newest.get(device.device_id)
        if prior is None or (reading.recorded_at, reading.reading_id) > (prior[0].recorded_at, prior[0].reading_id):
            newest[device.device_id] = (reading, device)
    for reading, device in newest.values():
        recorded_at = reading.recorded_at.replace(tzinfo=timezone.utc) if reading.recorded_at.tzinfo is None else reading.recorded_at.astimezone(timezone.utc)
        connection_manager.publish({"event": config.event, "device_id": device.device_id, "module": module, "reading_id": reading.reading_id, "value": getattr(reading, config.value_field), "status": config.status_for_value(getattr(reading, config.value_field), device.is_active), "source": ReadingSource.CSV_UPLOAD.value, "recorded_at": recorded_at.isoformat()})
    connection_manager.publish({"event": "DASHBOARD_UPDATE", "summary": get_dashboard_summary(database).model_dump(mode="json")})


def publish_dashboard_update(database: Session) -> None:
    """Publish one post-commit dashboard snapshot when clients are listening."""
    if connection_manager.client_count:
        connection_manager.publish({"event": "DASHBOARD_UPDATE", "summary": get_dashboard_summary(database).model_dump(mode="json")})


def publish_readings_reset() -> None:
    """Notify clients to discard cached readings after a successful reset."""
    if connection_manager.client_count:
        connection_manager.publish({"event": "READINGS_RESET"})
