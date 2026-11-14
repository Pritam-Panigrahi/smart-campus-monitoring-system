"""Pydantic schemas for simulation control endpoints."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.schemas.devices import SchemaBase


class SimulationMode(str, Enum):
    """The available timing profiles for simulated readings."""

    DEMO = "DEMO"
    REAL_TIME = "REAL_TIME"


class SimulationModeUpdate(SchemaBase):
    """Request body used to change the simulation timing profile."""

    mode: SimulationMode


class SimulationModuleStatus(SchemaBase):
    """Scheduling details for one independently running module."""

    interval_seconds: int = Field(ge=1)
    job_id: str
    scheduled: bool


class SimulationStatusResponse(SchemaBase):
    """Process-local simulation state, distinct from persisted reading history."""

    running: bool
    mode: SimulationMode
    modules: dict[str, SimulationModuleStatus]
    scheduled_job_count: int = Field(ge=0)
    historical_readings_count: int = Field(
        ge=0,
        description="Persisted readings in the database; this does not indicate whether simulation is running.",
    )
