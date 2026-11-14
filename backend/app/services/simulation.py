"""APScheduler-backed, append-only simulated monitoring readings."""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import desc, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AQIReading, AQIStation, ReadingSource, WasteBin, WasteBinReading, WaterTank, WaterTankReading
from app.schemas.simulation import SimulationMode, SimulationModuleStatus
from app.services.readings import append_reading


logger = logging.getLogger(__name__)

MODULES = ("water_tanks", "waste_bins", "aqi_stations")
JOB_IDS = {
    "water_tanks": "simulation-water-tanks",
    "waste_bins": "simulation-waste-bins",
    "aqi_stations": "simulation-aqi-stations",
}
INTERVALS: dict[SimulationMode, dict[str, int]] = {
    SimulationMode.DEMO: {"water_tanks": 5, "waste_bins": 10, "aqi_stations": 5},
    SimulationMode.REAL_TIME: {"water_tanks": 300, "waste_bins": 600, "aqi_stations": 300},
}


class SimulationService:
    """Own one scheduler and independently scheduled jobs for each device module."""

    def __init__(self) -> None:
        configured_mode = settings.simulation_default_mode
        self.mode = SimulationMode(configured_mode) if configured_mode in SimulationMode.__members__ else SimulationMode.DEMO
        self.scheduler = BackgroundScheduler(timezone=timezone.utc)
        self.running = False
        self._lock = RLock()
        # One barrier per module prevents overlapping module work. stop()
        # invalidates the active generation, then waits on every barrier before
        # reporting STOPPED.
        self._execution_locks = {module: RLock() for module in MODULES}
        self._generation = 0
        self._randomizers: dict[str, random.Random] = {}

    def initialize(self) -> None:
        """Start the scheduler infrastructure without scheduling simulation jobs."""
        with self._lock:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Simulation scheduler initialized; simulation remains stopped.")

    def shutdown(self) -> None:
        """Remove jobs and stop the scheduler during application shutdown."""
        self.stop()
        with self._lock:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            # APScheduler executors are terminal after shutdown. Recreate the
            # scheduler so a later FastAPI lifespan (tests or reload tooling)
            # can initialize safely without submitting work to a closed pool.
            self.scheduler = BackgroundScheduler(timezone=timezone.utc)
            logger.info("Simulation scheduler shut down cleanly.")

    def start(self) -> None:
        """Idempotently schedule all module jobs using the selected mode."""
        with self._lock:
            self.initialize()
            if self.running:
                logger.info("Simulation start requested while already running.")
                return
            self._generation += 1
            self.running = True
            self._schedule_all_jobs()
            logger.info("Simulation started in %s mode.", self.mode.value)

    def stop(self) -> None:
        """Cancel jobs and wait until a stale callback can no longer persist."""
        with self._lock:
            was_running = self.running
            # A callback captures its generation at scheduling time.  Bumping it
            # makes queued and rescheduled callbacks harmless before they write.
            self._generation += 1
            self.running = False
            for job_id in JOB_IDS.values():
                self.scheduler.remove_job(job_id) if self.scheduler.get_job(job_id) else None
        # Do not hold _lock here: an in-flight callback checks it between device
        # writes.  Acquiring this barrier means no callback can write after this
        # method returns.
        for execution_lock in self._execution_locks.values():
            with execution_lock:
                pass
        logger.info("Simulation %s.", "stopped" if was_running else "was already stopped")

    def set_mode(self, mode: SimulationMode) -> None:
        """Set a timing profile and atomically reschedule running module jobs."""
        with self._lock:
            self.mode = mode
            if self.running:
                self._generation += 1
                self._schedule_all_jobs()
                logger.info("Simulation rescheduled in %s mode.", self.mode.value)
            else:
                logger.info("Simulation mode set to %s while stopped.", self.mode.value)

    def status_modules(self) -> dict[str, SimulationModuleStatus]:
        """Return the current timing and scheduled state for every module."""
        intervals = INTERVALS[self.mode]
        return {
            module: SimulationModuleStatus(
                interval_seconds=intervals[module],
                job_id=JOB_IDS[module],
                scheduled=self.scheduler.get_job(JOB_IDS[module]) is not None,
            )
            for module in MODULES
        }

    def _schedule_all_jobs(self) -> None:
        """Replace all jobs so a mode switch can never accumulate duplicates."""
        generation = self._generation
        jobs: dict[str, Callable[[], None]] = {
            "water_tanks": lambda: self._run_module("water_tanks", self._generate_water_tank_readings, generation),
            "waste_bins": lambda: self._run_module("waste_bins", self._generate_waste_bin_readings, generation),
            "aqi_stations": lambda: self._run_module("aqi_stations", self._generate_aqi_readings, generation),
        }
        for module, job in jobs.items():
            self.scheduler.add_job(
                job,
                trigger="interval",
                seconds=INTERVALS[self.mode][module],
                id=JOB_IDS[module],
                name=f"Simulate {module}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=datetime.now(timezone.utc),
            )

    def _randomizer_for(self, device_id: str) -> random.Random:
        """Keep each device's random sequence independent and reproducible per process."""
        if device_id not in self._randomizers:
            self._randomizers[device_id] = random.Random(f"smart-campus:{device_id}")
        return self._randomizers[device_id]

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _next_float(self, device_id: str, previous: float | None, baseline: float, low_delta: float, high_delta: float) -> float:
        """Produce a bounded, gradual float movement for one device."""
        generator = self._randomizer_for(device_id)
        anchor = baseline + generator.uniform(-8, 8) if previous is None else previous
        return round(self._clamp(anchor + generator.uniform(low_delta, high_delta), 0, 100), 2)

    def _next_aqi(self, device_id: str, previous: int | None) -> int:
        """Produce a bounded, gradual AQI movement for one station."""
        generator = self._randomizer_for(device_id)
        anchor = 85 + generator.uniform(-20, 20) if previous is None else previous
        return int(round(self._clamp(anchor + generator.uniform(-12, 12), 0, 500)))

    def _run_water_tanks_job(self) -> None:
        self._run_module("water_tanks", self._generate_water_tank_readings, self._generation)

    def _run_waste_bins_job(self) -> None:
        self._run_module("waste_bins", self._generate_waste_bin_readings, self._generation)

    def _run_aqi_stations_job(self) -> None:
        self._run_module("aqi_stations", self._generate_aqi_readings, self._generation)

    def _is_generation_active(self, generation: int) -> bool:
        with self._lock:
            return self.running and self._generation == generation

    def _run_module(self, module: str, generator: Callable[[int | None], int], generation: int) -> None:
        """Contain a module failure so APScheduler keeps the other jobs alive."""
        if not self._is_generation_active(generation):
            return
        try:
            with self._execution_locks[module]:
                # It may have waited behind another module while Stop or a mode
                # change occurred.  Check again before opening a DB session.
                if not self._is_generation_active(generation):
                    return
                generated = generator(generation)
            logger.info("Simulation job %s generated %d readings.", module, generated)
        except Exception:
            logger.exception("Simulation job %s failed; other modules remain scheduled.", module)

    def _generate_water_tank_readings(self, generation: int | None = None) -> int:
        """Append one simulated reading for each active water tank."""
        return self._generate_module_readings(
            WaterTank,
            WaterTankReading,
            "tank_id",
            "water_percentage",
            lambda device, previous: self._next_float(device.device_id, previous, 62, -4, 2), generation,
        )

    def _generate_waste_bin_readings(self, generation: int | None = None) -> int:
        """Append one simulated reading for each active waste bin."""
        return self._generate_module_readings(
            WasteBin,
            WasteBinReading,
            "bin_id",
            "fill_percentage",
            lambda device, previous: self._next_float(device.device_id, previous, 38, -1, 5), generation,
        )

    def _generate_aqi_readings(self, generation: int | None = None) -> int:
        """Append one simulated reading for each active AQI station."""
        return self._generate_module_readings(
            AQIStation,
            AQIReading,
            "station_id",
            "current_aqi",
            lambda device, previous: self._next_aqi(device.device_id, previous), generation,
        )

    def _generate_module_readings(
        self,
        device_model: Any,
        reading_model: Any,
        parent_field: str,
        value_field: str,
        next_value: Callable[[Any, Any], float | int],
        generation: int | None = None,
    ) -> int:
        """Generate independently, logging device-specific failures without stopping a job."""
        generated = 0
        with SessionLocal() as database:
            devices = database.scalars(select(device_model).where(device_model.is_active.is_(True))).all()
            for device in devices:
                if generation is not None and not self._is_generation_active(generation):
                    logger.info("Simulation job cancelled before persisting remaining %s readings.", device_model.__tablename__)
                    break
                try:
                    parent_id = getattr(device, parent_field)
                    previous = database.scalar(
                        select(getattr(reading_model, value_field))
                        .where(getattr(reading_model, parent_field) == parent_id)
                        .order_by(desc(reading_model.recorded_at), desc(reading_model.reading_id))
                        .limit(1)
                    )
                    value = next_value(device, previous)
                    append_reading(
                        database,
                        device,
                        reading_model,
                        parent_field,
                        {value_field: value, "source": ReadingSource.SIMULATED},
                    )
                    generated += 1
                    logger.debug("Generated simulated %s reading for %s: %s", value_field, device.device_id, value)
                except Exception:
                    database.rollback()
                    logger.exception("Could not generate a simulated reading for %s.", device.device_id)
        return generated


simulation_service = SimulationService()
