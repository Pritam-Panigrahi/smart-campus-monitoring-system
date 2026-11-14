"""Historical monitoring-data import, preview, export, and reset endpoints."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.routes.readings import normalise_query_timestamp
from app.models import AQIReading, ReadingSource, WasteBinReading, WaterTankReading
from app.schemas.data_management import ResetReadingsRequest
from app.services.data_management import MAX_CSV_SIZE, add_readings, module_config, parse_csv, publish_dashboard_update, publish_import, publish_readings_reset
from app.services.simulation import simulation_service

router = APIRouter(tags=["Data management"])
logger = logging.getLogger(__name__)


class ImportMode(str, Enum):
    ADD = "ADD"
    REPLACE = "REPLACE"


async def read_csv_upload(file: UploadFile) -> bytes:
    """Bound multipart upload reads before parsing untrusted CSV data."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a .csv file.")
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload must use a CSV content type.")
    content = await file.read(MAX_CSV_SIZE + 1)
    if len(content) > MAX_CSV_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV files may not exceed 5 MB.")
    return content


@router.post("/data-management/preview/{module}", summary="Validate a CSV without writing readings")
async def preview_csv(module: str, file: UploadFile = File(...), database: Session = Depends(get_db)) -> dict[str, Any]:
    config = module_config(module)
    valid, errors, total = parse_csv(await read_csv_upload(file), config, database)
    return {"module": module, "total_rows": total, "valid_rows": len(valid), "invalid_rows": len(errors), "errors": errors, "preview": [{"device_id": row["device_id"], config.value_field: row["value"], "recorded_at": row["recorded_at"].isoformat(), "source": ReadingSource.CSV_UPLOAD.value} for row in valid[:100]]}


@router.post("/data-management/import/{module}", status_code=status.HTTP_201_CREATED, summary="Atomically import CSV readings")
async def import_csv(module: str, mode: ImportMode = Query(ImportMode.ADD), file: UploadFile = File(...), database: Session = Depends(get_db)) -> dict[str, Any]:
    config = module_config(module)
    if mode is ImportMode.REPLACE and simulation_service.running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "Simulation is running. Stop simulation before a REPLACE import; it will not be stopped automatically.", "simulation_running": True})
    valid, errors, total = parse_csv(await read_csv_upload(file), config, database)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"message": "CSV validation failed; no readings were imported.", "total_rows": total, "valid_rows": len(valid), "invalid_rows": len(errors), "errors": errors})
    created = add_readings(database, config, valid, mode is ImportMode.REPLACE)
    publish_import(database, module, config, created)
    return {"module": module, "mode": mode.value, "imported_rows": len(created), "simulation_running": simulation_service.running, "warning": "REPLACE affects only this module and simulation is not restarted automatically." if mode is ImportMode.REPLACE else None}


def filtered_statement(module: str, config: Any, device_id: str | None, start_date: datetime | None, end_date: datetime | None, source: ReadingSource | None) -> Any:
    reading, device = config.reading_model, config.model
    # Start from the module's reading model explicitly.  This keeps the device
    # join and its filter bound to the selected module for both table and CSV
    # queries, even though each module uses a different parent key.
    statement = select(reading, device.device_id, getattr(device, config.name_field), device.is_active).select_from(reading).join(device, getattr(reading, config.parent_field) == getattr(device, config.parent_field))
    device_id = device_id.strip() if device_id else None
    if device_id:
        statement = statement.where(device.device_id == device_id)
    if start_date:
        statement = statement.where(reading.recorded_at >= start_date)
    if end_date:
        statement = statement.where(reading.recorded_at <= end_date)
    if source:
        statement = statement.where(reading.source == source)
    return statement


def validate_dates(start_date: datetime | None, end_date: datetime | None) -> tuple[datetime | None, datetime | None]:
    start, end = normalise_query_timestamp(start_date, "start_date"), normalise_query_timestamp(end_date, "end_date")
    if start and end and start > end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date must be earlier than or equal to end_date.")
    return start, end


def row_data(module: str, config: Any, row: Any) -> dict[str, Any]:
    reading, device_id, device_name, is_active = row
    timestamp = reading.recorded_at.replace(tzinfo=timezone.utc) if reading.recorded_at.tzinfo is None else reading.recorded_at.astimezone(timezone.utc)
    value = getattr(reading, config.value_field)
    return {"reading_id": reading.reading_id, "device_id": device_id, "device_name": device_name, "module": module, config.value_field: value, "status": config.status_for_value(value, is_active), "source": reading.source.value if isinstance(reading.source, ReadingSource) else reading.source, "recorded_at": timestamp.isoformat()}


@router.get("/data-management/stored/{module}", summary="List stored module readings")
def stored_readings(module: str, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500), device_id: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None, source: ReadingSource | None = None, database: Session = Depends(get_db)) -> dict[str, Any]:
    config = module_config(module); start, end = validate_dates(start_date, end_date)
    statement = filtered_statement(module, config, device_id, start, end, source)
    total = database.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = database.execute(statement.order_by(config.reading_model.recorded_at.desc(), config.reading_model.reading_id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"module": module, "page": page, "page_size": page_size, "total": total, "readings": [row_data(module, config, row) for row in rows]}


@router.get("/data-management/export/{module}", summary="Export stored readings as CSV")
def export_readings(module: str, device_id: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None, source: ReadingSource | None = None, database: Session = Depends(get_db)) -> Response:
    config = module_config(module); start, end = validate_dates(start_date, end_date)
    rows = database.execute(filtered_statement(module, config, device_id, start, end, source).order_by(config.reading_model.recorded_at.desc(), config.reading_model.reading_id.desc())).all()
    logger.info(
        "CSV export module=%s has_device_filter=%s start_utc=%s end_utc=%s source=%s rows=%d",
        module, bool(device_id), start.isoformat() if start else None, end.isoformat() if end else None,
        source.value if source else None, len(rows),
    )
    if not rows:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Export-Record-Count": "0"})
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=["device_id", "device_name", "module", config.value_field, "status", "source", "recorded_at"]); writer.writeheader()
    for row in rows:
        data = row_data(module, config, row); writer.writerow({key: data[key] for key in writer.fieldnames})
    export_date = datetime.now(timezone.utc).date().isoformat()
    filename = f"{module.replace('_', '-')}-readings-{export_date}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Export-Record-Count": str(len(rows))})


@router.post("/data-management/reset", summary="Transactionally remove only monitoring readings")
def reset_readings(payload: ResetReadingsRequest, database: Session = Depends(get_db)) -> dict[str, Any]:
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Set confirm to true to reset readings.")
    try:
        counts = {"water_tanks": database.query(WaterTankReading).delete(synchronize_session=False), "waste_bins": database.query(WasteBinReading).delete(synchronize_session=False), "aqi_stations": database.query(AQIReading).delete(synchronize_session=False)}
        database.commit()
    except Exception:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Reading reset failed; no data was removed.")
    publish_readings_reset()
    publish_dashboard_update(database)
    return {"deleted": counts, "simulation_running": simulation_service.running, "warning": "Simulation was not stopped or restarted."}
