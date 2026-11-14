"""Simulation scheduler status and control endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models import AQIReading, WasteBinReading, WaterTankReading
from app.schemas.simulation import SimulationModeUpdate, SimulationStatusResponse
from app.services.simulation import simulation_service


router = APIRouter(tags=["Simulation"])


def simulation_status(database: Session) -> SimulationStatusResponse:
    """Build scheduler state separately from persisted historical-reading count."""
    historical_count = sum(
        database.scalar(select(func.count()).select_from(model)) or 0
        for model in (WaterTankReading, WasteBinReading, AQIReading)
    )
    modules = simulation_service.status_modules()
    return SimulationStatusResponse(
        running=simulation_service.running,
        mode=simulation_service.mode,
        modules=modules,
        scheduled_job_count=sum(module.scheduled for module in modules.values()),
        historical_readings_count=historical_count,
    )


@router.get("/simulation/status", response_model=SimulationStatusResponse, summary="Get simulation status")
def get_simulation_status(database: Session = Depends(get_db)) -> SimulationStatusResponse:
    """Report process-local scheduler state and persisted reading history separately."""
    return simulation_status(database)


@router.post("/simulation/start", response_model=SimulationStatusResponse, summary="Start simulation")
def start_simulation(database: Session = Depends(get_db)) -> SimulationStatusResponse:
    """Idempotently start independent water, waste, and AQI simulation jobs."""
    simulation_service.start()
    return simulation_status(database)


@router.post("/simulation/stop", response_model=SimulationStatusResponse, summary="Stop simulation")
def stop_simulation(database: Session = Depends(get_db)) -> SimulationStatusResponse:
    """Idempotently stop all simulation jobs while retaining historical readings."""
    simulation_service.stop()
    return simulation_status(database)


@router.put("/simulation/mode", response_model=SimulationStatusResponse, summary="Change simulation timing mode")
def set_simulation_mode(payload: SimulationModeUpdate, database: Session = Depends(get_db)) -> SimulationStatusResponse:
    """Set DEMO or REAL_TIME timing and reschedule running jobs without duplication."""
    simulation_service.set_mode(payload.mode)
    return simulation_status(database)
