"""End-to-end monitoring workflow against an isolated seeded SQLite database."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.main import app
from app.models import AQIReading, AQIStation, ReadingSource, WasteBin, WasteBinReading, WaterTank, WaterTankReading
from app.services.simulation import simulation_service
import app.services.simulation as simulation_module
from seed_devices import AQI_STATIONS, WASTE_BINS, WATER_TANKS


class EndToEndWorkflowTests(unittest.TestCase):
    """Exercise the three supported modules without touching smart_campus.db."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.engine = create_engine(f"sqlite:///{Path(cls.directory.name) / 'workflow.db'}", connect_args={"check_same_thread": False})
        cls.sessions = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)
        from app.core.database import Base
        Base.metadata.create_all(cls.engine)
        cls.original_simulation_session_factory = simulation_module.SessionLocal
        simulation_module.SessionLocal = cls.sessions

        def override_get_db():
            with cls.sessions() as database:
                yield database

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        simulation_service.stop()
        cls.client.__exit__(None, None, None)
        app.dependency_overrides.pop(get_db, None)
        simulation_module.SessionLocal = cls.original_simulation_session_factory
        cls.engine.dispose()
        cls.directory.cleanup()

    def setUp(self) -> None:
        simulation_service.stop()
        with self.sessions() as database:
            for model in (WaterTankReading, WasteBinReading, AQIReading, WaterTank, WasteBin, AQIStation):
                database.execute(delete(model))
            database.add_all([WaterTank(device_id=device_id, tank_name=name, location_name="Gate", latitude=latitude, longitude=longitude) for device_id, name, latitude, longitude in WATER_TANKS])
            database.add_all([WasteBin(device_id=device_id, bin_name=name, location_name="Gate", latitude=latitude, longitude=longitude) for device_id, name, latitude, longitude in WASTE_BINS])
            database.add_all([AQIStation(device_id=device_id, station_name=name, location_name="Gate", latitude=latitude, longitude=longitude) for device_id, name, latitude, longitude in AQI_STATIONS])
            database.commit()

    def count(self, model) -> int:
        with self.sessions() as database:
            return database.scalar(select(func.count()).select_from(model)) or 0

    def test_seeded_inventory_simulation_dashboard_websocket_and_device_safety(self) -> None:
        self.assertEqual(len(self.client.get('/api/water-tanks').json()), 4)
        self.assertEqual(len(self.client.get('/api/waste-bins').json()), 4)
        self.assertEqual(len(self.client.get('/api/aqi-stations').json()), 2)

        started = self.client.post('/api/simulation/start')
        self.assertEqual(started.status_code, 200)
        self.assertTrue(started.json()['running'])
        self.assertEqual(started.json()['mode'], 'DEMO')
        self.assertEqual(started.json()['modules']['water_tanks']['interval_seconds'], 5)
        self.assertEqual(started.json()['modules']['waste_bins']['interval_seconds'], 10)
        self.assertEqual(started.json()['modules']['aqi_stations']['interval_seconds'], 5)
        # Keep the WebSocket fixture deterministic: startup is verified above;
        # manually generated readings below exercise the broadcast path.
        self.client.post('/api/simulation/stop')

        with self.client.websocket_connect('/ws/monitoring') as websocket:
            self.assertEqual(simulation_service._generate_water_tank_readings(), 4)
            self.assertEqual(simulation_service._generate_waste_bin_readings(), 4)
            self.assertEqual(simulation_service._generate_aqi_readings(), 2)
            events = [websocket.receive_json() for _ in range(20)]
        self.assertEqual({event['event'] for event in events if event['event'].endswith('_READING')}, {'WATER_TANK_READING', 'WASTE_BIN_READING', 'AQI_READING'})
        self.assertGreaterEqual(sum(event['event'] == 'DASHBOARD_UPDATE' for event in events), 1)
        # Demo scheduling runs an immediate batch; explicit generation above
        # confirms each module can also run independently.
        self.assertGreaterEqual(self.count(WaterTankReading), 4)
        self.assertGreaterEqual(self.count(WasteBinReading), 4)
        self.assertGreaterEqual(self.count(AQIReading), 2)

        dashboard = self.client.get('/api/dashboard/summary').json()
        self.assertEqual((dashboard['total_water_tanks'], dashboard['total_waste_bins'], dashboard['total_aqi_stations']), (4, 4, 2))
        self.assertTrue(all(item['latest_reading'] for item in dashboard['water_tanks'] + dashboard['waste_bins'] + dashboard['aqi_stations']))

        real_time = self.client.put('/api/simulation/mode', json={'mode': 'REAL_TIME'})
        self.assertEqual(real_time.status_code, 200)
        self.assertEqual(real_time.json()['modules']['water_tanks']['interval_seconds'], 300)
        self.assertEqual(real_time.json()['modules']['waste_bins']['interval_seconds'], 600)
        self.assertEqual(real_time.json()['modules']['aqi_stations']['interval_seconds'], 300)
        stopped = self.client.post('/api/simulation/stop')
        self.assertFalse(stopped.json()['running'])
        self.assertEqual(stopped.json()['scheduled_job_count'], 0)

        # Deactivation is non-destructive: historical readings remain queryable.
        deactivated = self.client.patch('/api/water-tanks/WT-001/status', json={'is_active': False})
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()['is_active'])
        self.assertGreaterEqual(len(self.client.get('/api/water-tanks/WT-001/readings').json()), 1)
        duplicate = self.client.post('/api/water-tanks', json={'device_id': 'WT-001', 'tank_name': 'Duplicate', 'location_name': 'Gate', 'latitude': 19, 'longitude': 84, 'is_active': True})
        self.assertEqual(duplicate.status_code, 409)
        invalid_coordinate = self.client.post('/api/water-tanks', json={'device_id': 'WT-999', 'tank_name': 'Bad coordinate', 'location_name': 'Gate', 'latitude': 91, 'longitude': 84, 'is_active': True})
        self.assertEqual(invalid_coordinate.status_code, 422)

    def test_status_boundaries_and_reset_only_remove_readings(self) -> None:
        values = [
            ('/api/water-tanks/WT-001/readings', {'water_percentage': 0, 'source': ReadingSource.SENSOR.value}, 'Critical'),
            ('/api/waste-bins/WB-001/readings', {'fill_percentage': 81, 'source': ReadingSource.SENSOR.value}, 'Full'),
            ('/api/aqi-stations/AQI-001/readings', {'current_aqi': 201, 'source': ReadingSource.SENSOR.value}, 'Poor'),
        ]
        for path, payload, _status in values:
            self.assertEqual(self.client.post(path, json=payload).status_code, 201)
        summary = self.client.get('/api/dashboard/summary').json()
        statuses = {item['device_id']: item['status'] for key in ('water_tanks', 'waste_bins', 'aqi_stations') for item in summary[key]}
        self.assertEqual((statuses['WT-001'], statuses['WB-001'], statuses['AQI-001']), tuple(item[2] for item in values))
        reset = self.client.post('/api/data-management/reset', json={'confirm': True})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual((self.count(WaterTankReading), self.count(WasteBinReading), self.count(AQIReading)), (0, 0, 0))
        self.assertEqual((len(self.client.get('/api/water-tanks').json()), len(self.client.get('/api/waste-bins').json()), len(self.client.get('/api/aqi-stations').json())), (4, 4, 2))

    def test_stop_waits_for_callbacks_and_invalidates_scheduled_generations(self) -> None:
        """Stop prevents future demo work and stale jobs after a mode switch."""
        started = self.client.post('/api/simulation/start').json()
        self.assertTrue(started['running'])
        self.assertEqual(started['scheduled_job_count'], 3)
        # Each module is scheduled immediately; wait briefly for its first batch.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not all(self.count(model) for model in (WaterTankReading, WasteBinReading, AQIReading)):
            time.sleep(0.02)
        self.assertTrue(all(self.count(model) for model in (WaterTankReading, WasteBinReading, AQIReading)))

        repeated_start = self.client.post('/api/simulation/start').json()
        self.assertTrue(repeated_start['running'])
        self.assertEqual(repeated_start['scheduled_job_count'], 3)
        stopped = self.client.post('/api/simulation/stop').json()
        counts_at_stop = tuple(self.count(model) for model in (WaterTankReading, WasteBinReading, AQIReading))
        self.assertFalse(stopped['running'])
        self.assertEqual(stopped['scheduled_job_count'], 0)
        # Longer than the 10-second Demo waste-bin interval: no stale callback
        # may append a reading after the stop response has completed.
        time.sleep(10.2)
        self.assertEqual(tuple(self.count(model) for model in (WaterTankReading, WasteBinReading, AQIReading)), counts_at_stop)
        self.assertFalse(self.client.post('/api/simulation/stop').json()['running'])

        self.client.put('/api/simulation/mode', json={'mode': 'REAL_TIME'})
        self.client.post('/api/simulation/start')
        old_generation = simulation_service._generation
        switched = self.client.put('/api/simulation/mode', json={'mode': 'DEMO'}).json()
        self.assertEqual(switched['scheduled_job_count'], 3)
        before_stale_callback = self.count(WaterTankReading)
        simulation_service._run_module('water_tanks', simulation_service._generate_water_tank_readings, old_generation)
        self.assertEqual(self.count(WaterTankReading), before_stale_callback)
        self.client.post('/api/simulation/stop')


if __name__ == '__main__':
    unittest.main()
