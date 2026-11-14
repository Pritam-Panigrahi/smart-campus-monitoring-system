"""Idempotently register the initial Smart Campus monitoring devices.

The seed only adds missing master devices. It never changes an existing device
and deliberately does not create monitoring readings.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AQIStation, WasteBin, WaterTank


WATER_TANKS = (
    ("WT-001", "Tank 01", 19.22709731728123, 84.74938722336404),
    ("WT-002", "Tank 02", 19.226667561650817, 84.75008044050614),
    ("WT-003", "Tank 03", 19.225999785292174, 84.74956227819568),
    ("WT-004", "Tank 04", 19.227173350848595, 84.75098022235608),
)
WASTE_BINS = (
    ("WB-001", "Bin 01", 19.226866837144982, 84.75003601173523),
    ("WB-002", "Bin 02", 19.22691549772816, 84.75122529910871),
    ("WB-003", "Bin 03", 19.22605598439059, 84.74983886485077),
    ("WB-004", "Bin 04", 19.226565081290733, 84.75268175538429),
)
AQI_STATIONS = (
    ("AQI-001", "AQI Station 01", 19.226294003922263, 84.75047956554812),
    ("AQI-002", "AQI Station 02", 19.22687606571203, 84.75295852071488),
)


def seed_devices(model: type[WaterTank] | type[WasteBin] | type[AQIStation], name_field: str, devices: Sequence[tuple[str, str, float, float]]) -> tuple[int, int]:
    """Insert missing devices and return counts of inserted and existing rows."""
    inserted = 0
    existing = 0

    with SessionLocal() as session:
        for device_id, device_name, latitude, longitude in devices:
            found = session.scalar(select(model).where(model.device_id == device_id))
            if found is not None:
                existing += 1
                continue

            session.add(
                model(
                    device_id=device_id,
                    **{name_field: device_name},
                    location_name="Gate",
                    latitude=latitude,
                    longitude=longitude,
                )
            )
            inserted += 1
        session.commit()

    return inserted, existing


def main() -> None:
    """Seed every requested master device and print a concise summary."""
    summaries = (
        ("water tanks", *seed_devices(WaterTank, "tank_name", WATER_TANKS)),
        ("waste bins", *seed_devices(WasteBin, "bin_name", WASTE_BINS)),
        ("AQI stations", *seed_devices(AQIStation, "station_name", AQI_STATIONS)),
    )

    total_inserted = 0
    total_existing = 0
    for label, inserted, existing in summaries:
        total_inserted += inserted
        total_existing += existing
        print(f"{label}: {inserted} inserted, {existing} already existing")
    print(f"total: {total_inserted} inserted, {total_existing} already existing")


if __name__ == "__main__":
    main()
