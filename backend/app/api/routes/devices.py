"""Device-management routes for water tanks, waste bins, and AQI stations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models import AQIStation, WasteBin, WaterTank
from app.schemas.devices import (
    AQIStationCreate,
    AQIStationResponse,
    AQIStationUpdate,
    DevicesSummaryResponse,
    DeviceStatusUpdate,
    DeviceTypeSummary,
    WasteBinCreate,
    WasteBinResponse,
    WasteBinUpdate,
    WaterTankCreate,
    WaterTankResponse,
    WaterTankUpdate,
)


router = APIRouter(tags=["Device management"])


def get_device_or_404(database: Session, model: Any, device_id: str, label: str) -> Any:
    """Retrieve a master device or return the standard missing-device response."""
    device = database.scalar(select(model).where(model.device_id == device_id))
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} '{device_id}' was not found.")
    return device


def device_id_exists(database: Session, device_id: str) -> bool:
    """Check every master table so device IDs remain API-globally unique."""
    return any(
        database.scalar(select(model.device_id).where(model.device_id == device_id)) is not None
        for model in (WaterTank, WasteBin, AQIStation)
    )


def create_device(database: Session, model: Any, payload: Any) -> Any:
    """Persist a new master device and turn database conflicts into HTTP 409."""
    if device_id_exists(database, payload.device_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Device ID '{payload.device_id}' already exists.")

    device = model(**payload.model_dump())
    database.add(device)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Device ID '{payload.device_id}' already exists.") from error
    database.refresh(device)
    return device


def update_device(database: Session, device: Any, payload: Any) -> Any:
    """Apply a validated full update without replacing the master record."""
    for field, value in payload.model_dump().items():
        setattr(device, field, value)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device update conflicts with existing data.") from error
    database.refresh(device)
    return device


def device_summary(database: Session, model: Any) -> DeviceTypeSummary:
    """Return inventory and active-device counts for one master table."""
    total = database.scalar(select(func.count()).select_from(model)) or 0
    active = database.scalar(select(func.count()).select_from(model).where(model.is_active.is_(True))) or 0
    return DeviceTypeSummary(total=total, active=active)


@router.get("/water-tanks", response_model=list[WaterTankResponse], summary="List water tanks")
def list_water_tanks(database: Session = Depends(get_db)) -> list[WaterTank]:
    """List all registered water tanks, including inactive records."""
    return list(database.scalars(select(WaterTank).order_by(WaterTank.device_id)).all())


@router.get("/water-tanks/{device_id}", response_model=WaterTankResponse, summary="Get a water tank")
def get_water_tank(device_id: str, database: Session = Depends(get_db)) -> WaterTank:
    """Get one water tank by its immutable device ID."""
    return get_device_or_404(database, WaterTank, device_id, "Water tank")


@router.post("/water-tanks", response_model=WaterTankResponse, status_code=status.HTTP_201_CREATED, summary="Create a water tank")
def create_water_tank(payload: WaterTankCreate, database: Session = Depends(get_db)) -> WaterTank:
    """Register a water tank without generating any readings."""
    return create_device(database, WaterTank, payload)


@router.put("/water-tanks/{device_id}", response_model=WaterTankResponse, summary="Update a water tank")
def update_water_tank(device_id: str, payload: WaterTankUpdate, database: Session = Depends(get_db)) -> WaterTank:
    """Replace the mutable water-tank fields while preserving its identity and readings."""
    return update_device(database, get_device_or_404(database, WaterTank, device_id, "Water tank"), payload)


@router.patch("/water-tanks/{device_id}/status", response_model=WaterTankResponse, summary="Set water-tank activation")
def set_water_tank_status(device_id: str, payload: DeviceStatusUpdate, database: Session = Depends(get_db)) -> WaterTank:
    """Activate or deactivate a tank without deleting its historical readings."""
    return update_device(database, get_device_or_404(database, WaterTank, device_id, "Water tank"), payload)


@router.get("/waste-bins", response_model=list[WasteBinResponse], summary="List waste bins")
def list_waste_bins(database: Session = Depends(get_db)) -> list[WasteBin]:
    """List all registered waste bins, including inactive records."""
    return list(database.scalars(select(WasteBin).order_by(WasteBin.device_id)).all())


@router.get("/waste-bins/{device_id}", response_model=WasteBinResponse, summary="Get a waste bin")
def get_waste_bin(device_id: str, database: Session = Depends(get_db)) -> WasteBin:
    """Get one waste bin by its immutable device ID."""
    return get_device_or_404(database, WasteBin, device_id, "Waste bin")


@router.post("/waste-bins", response_model=WasteBinResponse, status_code=status.HTTP_201_CREATED, summary="Create a waste bin")
def create_waste_bin(payload: WasteBinCreate, database: Session = Depends(get_db)) -> WasteBin:
    """Register a waste bin without generating any readings."""
    return create_device(database, WasteBin, payload)


@router.put("/waste-bins/{device_id}", response_model=WasteBinResponse, summary="Update a waste bin")
def update_waste_bin(device_id: str, payload: WasteBinUpdate, database: Session = Depends(get_db)) -> WasteBin:
    """Replace mutable waste-bin fields while preserving its identity and readings."""
    return update_device(database, get_device_or_404(database, WasteBin, device_id, "Waste bin"), payload)


@router.patch("/waste-bins/{device_id}/status", response_model=WasteBinResponse, summary="Set waste-bin activation")
def set_waste_bin_status(device_id: str, payload: DeviceStatusUpdate, database: Session = Depends(get_db)) -> WasteBin:
    """Activate or deactivate a bin without deleting its historical readings."""
    return update_device(database, get_device_or_404(database, WasteBin, device_id, "Waste bin"), payload)


@router.get("/aqi-stations", response_model=list[AQIStationResponse], summary="List AQI stations")
def list_aqi_stations(database: Session = Depends(get_db)) -> list[AQIStation]:
    """List all registered AQI stations, including inactive records."""
    return list(database.scalars(select(AQIStation).order_by(AQIStation.device_id)).all())


@router.get("/aqi-stations/{device_id}", response_model=AQIStationResponse, summary="Get an AQI station")
def get_aqi_station(device_id: str, database: Session = Depends(get_db)) -> AQIStation:
    """Get one AQI station by its immutable device ID."""
    return get_device_or_404(database, AQIStation, device_id, "AQI station")


@router.post("/aqi-stations", response_model=AQIStationResponse, status_code=status.HTTP_201_CREATED, summary="Create an AQI station")
def create_aqi_station(payload: AQIStationCreate, database: Session = Depends(get_db)) -> AQIStation:
    """Register an AQI station without generating any readings."""
    return create_device(database, AQIStation, payload)


@router.put("/aqi-stations/{device_id}", response_model=AQIStationResponse, summary="Update an AQI station")
def update_aqi_station(device_id: str, payload: AQIStationUpdate, database: Session = Depends(get_db)) -> AQIStation:
    """Replace mutable station fields while preserving its identity and readings."""
    return update_device(database, get_device_or_404(database, AQIStation, device_id, "AQI station"), payload)


@router.patch("/aqi-stations/{device_id}/status", response_model=AQIStationResponse, summary="Set AQI-station activation")
def set_aqi_station_status(device_id: str, payload: DeviceStatusUpdate, database: Session = Depends(get_db)) -> AQIStation:
    """Activate or deactivate a station without deleting its historical readings."""
    return update_device(database, get_device_or_404(database, AQIStation, device_id, "AQI station"), payload)


@router.get("/devices/summary", response_model=DevicesSummaryResponse, summary="Get device inventory summary")
def get_devices_summary(database: Session = Depends(get_db)) -> DevicesSummaryResponse:
    """Return total and active master-device counts grouped by type."""
    return DevicesSummaryResponse(
        water_tanks=device_summary(database, WaterTank),
        waste_bins=device_summary(database, WasteBin),
        aqi_stations=device_summary(database, AQIStation),
    )
