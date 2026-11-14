"""Isolated integration coverage for data-management APIs."""

from __future__ import annotations

import tempfile
import unittest
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.main import app
from app.models import AQIReading, AQIStation, ReadingSource, WasteBin, WasteBinReading, WaterTank, WaterTankReading


class DataManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.engine = create_engine(f"sqlite:///{Path(cls.directory.name) / 'data-management.db'}", connect_args={"check_same_thread": False})
        cls.sessions = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)
        from app.core.database import Base
        Base.metadata.create_all(cls.engine)

        def override_get_db():
            with cls.sessions() as database:
                yield database

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        app.dependency_overrides.pop(get_db, None)
        cls.engine.dispose()
        cls.directory.cleanup()

    def setUp(self) -> None:
        with self.sessions() as database:
            for model in (WaterTankReading, WasteBinReading, AQIReading, WaterTank, WasteBin, AQIStation):
                database.execute(delete(model))
            database.add_all([
                WaterTank(device_id="WT-1", tank_name="Tank", location_name="North", latitude=1, longitude=1),
                WasteBin(device_id="WB-1", bin_name="Bin", location_name="East", latitude=2, longitude=2),
                AQIStation(device_id="AQ-1", station_name="Air", location_name="West", latitude=3, longitude=3),
            ])
            database.commit()

    @staticmethod
    def csv_file(text: str):
        return {"file": ("readings.csv", text, "text/csv")}

    def count(self, model) -> int:
        with self.sessions() as database:
            return database.scalar(select(func.count()).select_from(model)) or 0

    def test_preview_add_export_and_filters_do_not_partially_write(self) -> None:
        csv = "device_id,water_percentage,recorded_at,source\nWT-1,62.5,2026-01-02T10:00:00+00:00,SENSOR\n"
        preview = self.client.post("/api/data-management/preview/water_tanks", files=self.csv_file(csv))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["valid_rows"], 1)
        self.assertEqual(self.count(WaterTankReading), 0)

        imported = self.client.post("/api/data-management/import/water_tanks?mode=ADD", files=self.csv_file(csv))
        self.assertEqual(imported.status_code, 201)
        self.assertEqual(imported.json()["imported_rows"], 1)
        self.assertEqual(self.count(WaterTankReading), 1)

        stored = self.client.get("/api/data-management/stored/water_tanks?device_id=WT-1&source=CSV_UPLOAD")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["total"], 1)
        self.assertEqual(stored.json()["readings"][0]["device_name"], "Tank")
        exported = self.client.get("/api/data-management/export/water_tanks?device_id=WT-1")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("water_percentage", exported.text)
        self.assertIn("CSV_UPLOAD", exported.text)

    def test_invalid_replace_preserves_existing_and_other_modules(self) -> None:
        with self.sessions() as database:
            tank = database.scalar(select(WaterTank).where(WaterTank.device_id == "WT-1"))
            waste_bin = database.scalar(select(WasteBin).where(WasteBin.device_id == "WB-1"))
            database.add_all([
                WaterTankReading(tank_id=tank.tank_id, water_percentage=20, source=ReadingSource.SENSOR),
                WasteBinReading(bin_id=waste_bin.bin_id, fill_percentage=30, source=ReadingSource.SENSOR),
            ])
            database.commit()
        invalid = "device_id,water_percentage,recorded_at\nMISSING,150,not-a-date\n"
        response = self.client.post("/api/data-management/import/water_tanks?mode=REPLACE", files=self.csv_file(invalid))
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["errors"][0]["row"], 2)
        self.assertEqual(self.count(WaterTankReading), 1)
        self.assertEqual(self.count(WasteBinReading), 1)

    def test_export_filters_csv_metadata_and_utc_boundaries(self) -> None:
        """Exercise every export module against the isolated SQLite database."""
        with self.sessions() as database:
            aqi_two = database.scalar(select(AQIStation).where(AQIStation.device_id == "AQ-1"))
            aqi_two.device_id = "AQI-002"
            aqi_two.station_name = "AQI Station 2"
            database.add(AQIStation(device_id="AQI-003", station_name="AQI Station 3", location_name="South", latitude=4, longitude=4))
            database.flush()
            aqi_three = database.scalar(select(AQIStation).where(AQIStation.device_id == "AQI-003"))
            tank = database.scalar(select(WaterTank).where(WaterTank.device_id == "WT-1"))
            waste_bin = database.scalar(select(WasteBin).where(WasteBin.device_id == "WB-1"))
            database.add_all([
                # 15:31 in Kolkata is 10:01 UTC. The middle record proves that
                # the frontend's minute-inclusive end timestamp is honoured.
                AQIReading(station_id=aqi_two.station_id, current_aqi=71, source=ReadingSource.SENSOR, recorded_at=datetime(2026, 11, 14, 10, 1, 0, tzinfo=timezone.utc)),
                AQIReading(station_id=aqi_two.station_id, current_aqi=72, source=ReadingSource.SENSOR, recorded_at=datetime(2026, 11, 14, 10, 1, 42, tzinfo=timezone.utc)),
                AQIReading(station_id=aqi_two.station_id, current_aqi=73, source=ReadingSource.SENSOR, recorded_at=datetime(2026, 11, 14, 10, 1, 59, 999000, tzinfo=timezone.utc)),
                AQIReading(station_id=aqi_three.station_id, current_aqi=88, source=ReadingSource.SIMULATED, recorded_at=datetime(2026, 11, 14, 10, 1, 30, tzinfo=timezone.utc)),
                WaterTankReading(tank_id=tank.tank_id, water_percentage=54.5, source=ReadingSource.SENSOR, recorded_at=datetime(2026, 11, 14, 10, 1, 30, tzinfo=timezone.utc)),
                WasteBinReading(bin_id=waste_bin.bin_id, fill_percentage=64.5, source=ReadingSource.CSV_UPLOAD, recorded_at=datetime(2026, 11, 14, 10, 1, 30, tzinfo=timezone.utc)),
            ])
            database.commit()

        all_aqi = self.client.get("/api/data-management/export/aqi_stations")
        self.assertEqual(all_aqi.status_code, 200)
        self.assertEqual(all_aqi.headers["content-type"], "text/csv; charset=utf-8")
        self.assertEqual(all_aqi.headers["x-export-record-count"], "4")
        self.assertRegex(all_aqi.headers["content-disposition"], r'filename="aqi-stations-readings-\d{4}-\d{2}-\d{2}\.csv"')
        all_rows = list(csv.DictReader(io.StringIO(all_aqi.text)))
        self.assertEqual({row["device_id"] for row in all_rows}, {"AQI-002", "AQI-003"})
        self.assertEqual(all_rows[0].keys(), {"device_id", "device_name", "module", "current_aqi", "status", "source", "recorded_at"})

        only_aqi_two = self.client.get("/api/data-management/export/aqi_stations?device_id=AQI-002")
        self.assertEqual(only_aqi_two.headers["x-export-record-count"], "3")
        self.assertEqual({row["device_id"] for row in csv.DictReader(io.StringIO(only_aqi_two.text))}, {"AQI-002"})

        # Equivalent to the frontend request for identical 2026-11-14 15:31
        # datetime-local inputs in Asia/Kolkata: start inclusive, end inclusive.
        minute = self.client.get("/api/data-management/export/aqi_stations?device_id=AQI-002&start_date=2026-11-14T15%3A31%3A00%2B05%3A30&end_date=2026-11-14T15%3A31%3A59.999%2B05%3A30")
        self.assertEqual(minute.status_code, 200)
        self.assertEqual(minute.headers["x-export-record-count"], "3")

        # Bounds are inclusive even at the exact UTC start and end timestamps.
        exact = self.client.get("/api/data-management/export/aqi_stations?device_id=AQI-002&start_date=2026-11-14T10%3A01%3A00Z&end_date=2026-11-14T10%3A01%3A00Z")
        self.assertEqual(exact.headers["x-export-record-count"], "1")

        for module, value_field, expected_device in (("water_tanks", "water_percentage", "WT-1"), ("waste_bins", "fill_percentage", "WB-1")):
            response = self.client.get(f"/api/data-management/export/{module}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["x-export-record-count"], "1")
            row = next(csv.DictReader(io.StringIO(response.text)))
            self.assertEqual(row["device_id"], expected_device)
            self.assertIn(value_field, row)

        empty = self.client.get("/api/data-management/export/aqi_stations?device_id=DOES-NOT-EXIST")
        self.assertEqual(empty.status_code, 204)
        self.assertEqual(empty.headers["x-export-record-count"], "0")
        self.assertEqual(empty.content, b"")

    def test_export_matches_filtered_stored_data_and_is_not_paginated(self) -> None:
        """A CSV export must use every Stored Data filter but never its page limit."""
        with self.sessions() as database:
            database.add(WaterTank(device_id="WT-004", tank_name="Tank 04", location_name="South", latitude=4, longitude=4))
            database.flush()
            tank = database.scalar(select(WaterTank).where(WaterTank.device_id == "WT-004"))
            database.add_all([
                WaterTankReading(tank_id=tank.tank_id, water_percentage=50 + index, source=ReadingSource.SENSOR, recorded_at=datetime(2026, 11, 14, 10, index, tzinfo=timezone.utc))
                for index in range(5)
            ])
            # This row proves source filtering is shared by the table and CSV.
            database.add(WaterTankReading(tank_id=tank.tank_id, water_percentage=99, source=ReadingSource.SIMULATED, recorded_at=datetime(2026, 11, 14, 10, 2, tzinfo=timezone.utc)))
            database.commit()

        filters = "device_id=WT-004&start_date=2026-11-14T10%3A00%3A00Z&end_date=2026-11-14T10%3A04%3A59.999Z&source=SENSOR"
        stored = self.client.get(f"/api/data-management/stored/water_tanks?{filters}&page=1&page_size=2")
        exported = self.client.get(f"/api/data-management/export/water_tanks?{filters}", headers={"Origin": "http://localhost:5173"})

        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["total"], 5)
        self.assertEqual(len(stored.json()["readings"]), 2)
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.headers["x-export-record-count"], "5")
        self.assertIn("X-Export-Record-Count", exported.headers["access-control-expose-headers"])
        rows = list(csv.DictReader(io.StringIO(exported.text)))
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["device_id"] for row in rows}, {"WT-004"})
        self.assertEqual({row["source"] for row in rows}, {"SENSOR"})

    def test_export_device_and_all_device_filters_for_every_module(self) -> None:
        """CSV and Stored Data share filters for water, waste, and AQI modules."""
        module_cases = (
            ("water_tanks", WaterTank, WaterTankReading, "tank_id", "tank_name", "water_percentage", "WT-001", "WT-002", 40),
            ("waste_bins", WasteBin, WasteBinReading, "bin_id", "bin_name", "fill_percentage", "WB-001", "WB-002", 40),
            ("aqi_stations", AQIStation, AQIReading, "station_id", "station_name", "current_aqi", "AQI-001", "AQI-002", 40),
        )
        with self.sessions() as database:
            for _, device_model, reading_model, parent_field, name_field, value_field, first_id, second_id, base_value in module_cases:
                first = database.scalar(select(device_model).limit(1))
                first.device_id = first_id
                setattr(first, name_field, f"{first_id} device")
                second = device_model(device_id=second_id, location_name="South", latitude=5, longitude=5, **{name_field: f"{second_id} device"})
                database.add(second)
                database.flush()
                for device, offset in ((first, 0), (second, 10)):
                    for minute in range(2):
                        database.add(reading_model(**{parent_field: getattr(device, parent_field), value_field: base_value + offset + minute, "source": ReadingSource.SENSOR, "recorded_at": datetime(2026, 11, 14, 10, minute, tzinfo=timezone.utc)}))
            database.commit()

        shared_filters = "start_date=2026-11-14T10%3A00%3A00Z&end_date=2026-11-14T10%3A01%3A59.999Z&source=SENSOR"
        for module, _, _, _, _, _, first_id, second_id, _ in module_cases:
            # The stored table intentionally fetches a page, while CSV must
            # contain all matching readings for that same device/filter set.
            stored = self.client.get(f"/api/data-management/stored/{module}?device_id={first_id}&{shared_filters}&page=1&page_size=1")
            all_stored = self.client.get(f"/api/data-management/stored/{module}?{shared_filters}&page=1&page_size=500")
            selected_export = self.client.get(f"/api/data-management/export/{module}?device_id={first_id}&{shared_filters}")
            all_devices_export = self.client.get(f"/api/data-management/export/{module}?{shared_filters}")

            self.assertEqual(stored.status_code, 200, module)
            self.assertEqual(stored.json()["total"], 2, module)
            self.assertEqual(len(stored.json()["readings"]), 1, module)
            selected_rows = list(csv.DictReader(io.StringIO(selected_export.text)))
            self.assertEqual(selected_export.headers["x-export-record-count"], "2", module)
            self.assertEqual(len(selected_rows), 2, module)
            self.assertEqual({row["device_id"] for row in selected_rows}, {first_id}, module)

            all_rows = list(csv.DictReader(io.StringIO(all_devices_export.text)))
            self.assertEqual(all_stored.status_code, 200, module)
            self.assertEqual(all_stored.json()["total"], 4, module)
            self.assertEqual(all_devices_export.headers["x-export-record-count"], "4", module)
            self.assertEqual(len(all_rows), 4, module)
            self.assertEqual({row["device_id"] for row in all_rows}, {first_id, second_id}, module)
            self.assertEqual({row["source"] for row in all_rows}, {"SENSOR"}, module)
            self.assertEqual(
                {row["device_id"] for row in all_stored.json()["readings"]},
                {row["device_id"] for row in all_rows},
                module,
            )

    def test_replace_reset_confirmation_and_success_only_broadcast(self) -> None:
        initial = "device_id,water_percentage,recorded_at\nWT-1,10,2026-01-01T00:00:00+00:00\n"
        replacement = "device_id,water_percentage,recorded_at\nWT-1,90,2026-01-03T00:00:00+00:00\n"
        self.client.post("/api/data-management/import/water_tanks", files=self.csv_file(initial))
        with patch("app.services.data_management.connection_manager.publish") as publish:
            response = self.client.post("/api/data-management/import/water_tanks?mode=REPLACE", files=self.csv_file(replacement))
            self.assertEqual(response.status_code, 201)
            self.assertEqual(self.count(WaterTankReading), 1)
            # With no WebSocket clients, import produces no live events.
            publish.assert_not_called()
        denied = self.client.post("/api/data-management/reset", json={"confirm": False})
        self.assertEqual(denied.status_code, 422)
        self.assertEqual(self.count(WaterTankReading), 1)
        reset = self.client.post("/api/data-management/reset", json={"confirm": True})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["deleted"]["water_tanks"], 1)
        self.assertEqual(self.count(WaterTankReading), 0)
        # Master devices are deliberately untouched.
        with self.sessions() as database:
            self.assertEqual(database.scalar(select(func.count()).select_from(WaterTank)), 1)


if __name__ == "__main__":
    unittest.main()
