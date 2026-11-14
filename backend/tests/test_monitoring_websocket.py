"""Integration tests for monitoring WebSocket events using an isolated SQLite database."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_db
from app.main import app
from app.models import AQIStation, ReadingSource, WasteBin, WaterTank
from app.models.monitoring import AQIReading, WasteBinReading, WaterTankReading
from app.services.simulation import simulation_service
from app.websockets.monitoring import connection_manager
import app.services.simulation as simulation_module


class FailingWebSocket:
    async def send_json(self, _event: dict[str, object]) -> None:
        raise RuntimeError("simulated client send failure")


class MonitoringWebSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.database_path = Path(cls.temp_directory.name) / "monitoring-test.db"
        cls.engine = create_engine(f"sqlite:///{cls.database_path}", connect_args={"check_same_thread": False})
        cls.session_factory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)
        from app.core.database import Base

        Base.metadata.create_all(cls.engine)
        cls.original_simulation_session_factory = simulation_module.SessionLocal
        simulation_module.SessionLocal = cls.session_factory

        def override_get_db():
            with cls.session_factory() as database:
                yield database

        cls.override_get_db = override_get_db
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        app.dependency_overrides.pop(get_db, None)
        simulation_module.SessionLocal = cls.original_simulation_session_factory
        cls.engine.dispose()
        cls.temp_directory.cleanup()

    def setUp(self) -> None:
        self.assertEqual(connection_manager.client_count, 0)
        with self.session_factory() as database:
            for model in (WaterTankReading, WasteBinReading, AQIReading, WaterTank, WasteBin, AQIStation):
                database.execute(delete(model))
            database.add_all(
                [
                    WaterTank(
                        device_id="TANK-1",
                        tank_name="Tank 1",
                        location_name="North",
                        latitude=1,
                        longitude=1,
                    ),
                    WasteBin(
                        device_id="BIN-1",
                        bin_name="Bin 1",
                        location_name="East",
                        latitude=2,
                        longitude=2,
                    ),
                    AQIStation(
                        device_id="AQI-1",
                        station_name="Station 1",
                        location_name="South",
                        latitude=3,
                        longitude=3,
                    ),
                ]
            )
            database.commit()

    def test_multiple_clients_receive_all_reading_and_dashboard_events(self) -> None:
        cases = [
            (
                "TANK-1",
                {"water_percentage": 62.5, "source": ReadingSource.SENSOR.value},
                "WATER_TANK_READING",
                "water_tanks",
                62.5,
                "Normal",
            ),
            (
                "BIN-1",
                {"fill_percentage": 40, "source": ReadingSource.CSV_UPLOAD.value},
                "WASTE_BIN_READING",
                "waste_bins",
                40,
                "Medium",
            ),
            (
                "AQI-1",
                {"current_aqi": 85, "source": ReadingSource.SIMULATED.value},
                "AQI_READING",
                "aqi_stations",
                85,
                "Satisfactory",
            ),
        ]
        with self.client.websocket_connect("/ws/monitoring") as first, self.client.websocket_connect(
            "/ws/monitoring"
        ) as second:
            self.assertEqual(connection_manager.client_count, 2)
            for device_id, payload, event_name, module, value, status in cases:
                path = {
                    "TANK-1": "water-tanks",
                    "BIN-1": "waste-bins",
                    "AQI-1": "aqi-stations",
                }[device_id]
                response = self.client.post(f"/api/{path}/{device_id}/readings", json=payload)
                self.assertEqual(response.status_code, 201)
                for websocket in (first, second):
                    reading_event = websocket.receive_json()
                    dashboard_event = websocket.receive_json()
                    expected_recorded_at = datetime.fromisoformat(response.json()["recorded_at"].replace("Z", "+00:00"))
                    actual_recorded_at = datetime.fromisoformat(reading_event["recorded_at"].replace("Z", "+00:00"))
                    self.assertEqual(
                        reading_event,
                        {
                            "event": event_name,
                            "device_id": device_id,
                            "module": module,
                            "reading_id": response.json()["reading_id"],
                            "value": value,
                            "status": status,
                            "source": payload["source"],
                            "recorded_at": actual_recorded_at.isoformat(),
                        },
                    )
                    self.assertEqual(actual_recorded_at, expected_recorded_at)
                    self.assertEqual(dashboard_event["event"], "DASHBOARD_UPDATE")
                    self.assertIn("summary", dashboard_event)
                    dashboard_group = {
                        "water_tanks": "water_tanks",
                        "waste_bins": "waste_bins",
                        "aqi_stations": "aqi_stations",
                    }[module]
                    dashboard_device = dashboard_event["summary"][dashboard_group][0]
                    self.assertEqual(dashboard_device["latest_reading"]["reading_id"], reading_event["reading_id"])
                    self.assertGreaterEqual(
                        sum(
                            dashboard_event["summary"][key]
                            for key in ("total_water_tanks", "total_waste_bins", "total_aqi_stations")
                        ),
                        3,
                    )

    def test_connection_disconnect_and_failed_client_are_isolated(self) -> None:
        with self.client.websocket_connect("/ws/monitoring") as websocket:
            self.assertEqual(connection_manager.client_count, 1)
            failing_client = FailingWebSocket()
            with connection_manager._lock:
                connection_manager._clients.add(failing_client)  # type: ignore[arg-type]
            response = self.client.post(
                "/api/water-tanks/TANK-1/readings",
                json={"water_percentage": 55, "source": "SENSOR"},
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(websocket.receive_json()["event"], "WATER_TANK_READING")
            self.assertEqual(websocket.receive_json()["event"], "DASHBOARD_UPDATE")
            self.assertEqual(connection_manager.client_count, 1)
        self.assertEqual(connection_manager.client_count, 0)

    def test_failed_reading_creation_does_not_publish(self) -> None:
        with patch("app.services.readings.connection_manager.publish") as publish:
            response = self.client.post(
                "/api/water-tanks/TANK-1/readings",
                json={"water_percentage": 101, "source": "SENSOR"},
            )
            self.assertEqual(response.status_code, 422)
            publish.assert_not_called()

            response = self.client.post(
                "/api/water-tanks/MISSING/readings",
                json={"water_percentage": 40, "source": "SENSOR"},
            )
            self.assertEqual(response.status_code, 404)
            publish.assert_not_called()

            with patch.object(Session, "commit", side_effect=RuntimeError("simulated database failure")):
                with self.assertRaises(RuntimeError):
                    self.client.post(
                        "/api/water-tanks/TANK-1/readings",
                        json={"water_percentage": 40, "source": "SENSOR"},
                    )
            publish.assert_not_called()

    def test_simulation_generated_reading_uses_live_broadcast_path(self) -> None:
        with self.client.websocket_connect("/ws/monitoring") as websocket:
            self.assertEqual(simulation_service._generate_water_tank_readings(), 1)
            reading_event = websocket.receive_json()
            dashboard_event = websocket.receive_json()
            self.assertEqual(reading_event["event"], "WATER_TANK_READING")
            self.assertEqual(reading_event["device_id"], "TANK-1")
            self.assertEqual(reading_event["source"], "SIMULATED")
            self.assertEqual(dashboard_event["event"], "DASHBOARD_UPDATE")

    def test_reset_broadcasts_reading_invalidation_and_empty_dashboard(self) -> None:
        self.client.post("/api/water-tanks/TANK-1/readings", json={"water_percentage": 90, "source": "SENSOR"})
        with self.client.websocket_connect("/ws/monitoring") as websocket:
            response = self.client.post("/api/data-management/reset", json={"confirm": True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(websocket.receive_json(), {"event": "READINGS_RESET"})
            dashboard_event = websocket.receive_json()
            self.assertEqual(dashboard_event["event"], "DASHBOARD_UPDATE")
            self.assertIsNone(dashboard_event["summary"]["water_tanks"][0]["latest_reading"])

    def test_health_dashboard_and_simulation_controls_still_work(self) -> None:
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        dashboard = self.client.get("/api/dashboard/summary")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["total_water_tanks"], 1)

        self.assertEqual(self.client.put("/api/simulation/mode", json={"mode": "REAL_TIME"}).status_code, 200)
        with patch.object(simulation_service, "_schedule_all_jobs"):
            started = self.client.post("/api/simulation/start")
            self.assertEqual(started.status_code, 200)
            self.assertTrue(started.json()["running"])
            stopped = self.client.post("/api/simulation/stop")
        self.assertEqual(stopped.status_code, 200)
        self.assertFalse(stopped.json()["running"])
        self.client.put("/api/simulation/mode", json={"mode": "DEMO"})


if __name__ == "__main__":
    unittest.main()
