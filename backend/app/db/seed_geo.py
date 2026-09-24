"""Reproducible, explicitly fictional Moscow infrastructure for local demos."""

import math
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InfrastructureObject, NetworkEdge, SensorChannel, TelemetryEvent
from app.db.session import SessionLocal

# Approximate district anchors only. Neither points nor links represent real utilities.
DISTRICTS = [
    ("ЦАО", 37.6173, 55.7558),
    ("САО", 37.5320, 55.8460),
    ("СВАО", 37.6730, 55.8490),
    ("ВАО", 37.7890, 55.7850),
    ("ЮВАО", 37.7580, 55.7000),
    ("ЮАО", 37.6350, 55.6530),
    ("ЮЗАО", 37.5170, 55.6810),
    ("ЗАО", 37.4430, 55.7410),
    ("СЗАО", 37.4520, 55.8220),
]

TYPES = [
    ("collector", "Коллектор", "12"),
    ("pump", "Насосная станция", "7"),
    ("ventilation", "Вентшахта", "8"),
    ("power", "Электроузел", "9"),
    ("monitoring", "Пост мониторинга", "4"),
]


def seed_geo_demo(session: Session) -> dict[str, int]:
    if session.scalar(select(InfrastructureObject.id).where(InfrastructureObject.is_demo).limit(1)):
        return {"objects": 0, "channels": 0, "events": 0, "edges": 0}

    rng = random.Random(2026)
    now = datetime.now(tz=UTC).replace(minute=0, second=0, microsecond=0)
    objects: list[InfrastructureObject] = []
    channels: list[SensorChannel] = []
    events: list[TelemetryEvent] = []
    edges: list[NetworkEdge] = []

    for district_index, (district, hub_lng, hub_lat) in enumerate(DISTRICTS, start=1):
        hub_id = f"DEMO-HUB-{district_index:02d}"
        objects.append(
            InfrastructureObject(
                id=hub_id,
                name=f"Опорный узел {district}",
                system_name="Магистральный коллектор",
                tag=hub_id,
                district=district,
                object_type="hub",
                status="normal",
                latitude=hub_lat,
                longitude=hub_lng,
                is_demo=True,
            )
        )
        previous_id = hub_id
        for branch in range(1, 13):
            type_id, type_name, channel_type = TYPES[(branch + district_index) % len(TYPES)]
            angle = (2 * math.pi * branch / 12) + district_index * 0.29
            radius = 0.008 + (branch % 4) * 0.005 + rng.uniform(-0.002, 0.002)
            lng = round(hub_lng + math.cos(angle) * radius * 1.6, 6)
            lat = round(hub_lat + math.sin(angle) * radius, 6)
            object_id = f"DEMO-{district_index:02d}-{branch:02d}"
            status = "critical" if (district_index * 13 + branch) % 29 == 0 else (
                "attention" if (district_index * 13 + branch) % 7 == 0 else "normal"
            )
            objects.append(
                InfrastructureObject(
                    id=object_id,
                    name=f"{type_name} {district}-{branch:02d}",
                    system_name=type_name,
                    tag=object_id,
                    district=district,
                    object_type=type_id,
                    status=status,
                    latitude=lat,
                    longitude=lng,
                    is_demo=True,
                )
            )
            channel_id = f"DEMO-CH-{district_index:02d}-{branch:02d}"
            channels.append(
                SensorChannel(
                    id=channel_id,
                    object_tag=object_id,
                    channel_type=channel_type,
                    display_name=f"Датчик · {type_name} {district}-{branch:02d}",
                )
            )
            for day in range(14):
                value = round(19 + (branch % 6) * 2 + math.sin(day / 2 + branch) * 4, 2)
                if status == "critical" and day == 0:
                    value += 18
                events.append(
                    TelemetryEvent(
                        source_record_id=f"DEMO-E-{district_index:02d}-{branch:02d}-{day:02d}",
                        channel_id=channel_id,
                        channel_type=channel_type,
                        value_raw=str(value),
                        value_numeric=value,
                        occurred_at=now - timedelta(days=day, minutes=branch * 3),
                        import_batch_id=None,
                    )
                )
            edges.append(
                NetworkEdge(
                    id=f"DEMO-L-{district_index:02d}-{branch:02d}",
                    source_id=hub_id,
                    target_id=object_id,
                    kind="distribution",
                    is_demo=True,
                )
            )
            if branch % 3 == 0:
                edges.append(
                    NetworkEdge(
                        id=f"DEMO-R-{district_index:02d}-{branch:02d}",
                        source_id=previous_id,
                        target_id=object_id,
                        kind="collector",
                        is_demo=True,
                    )
                )
            previous_id = object_id

    for district_index in range(1, len(DISTRICTS) + 1):
        next_index = district_index % len(DISTRICTS) + 1
        edges.append(
            NetworkEdge(
                id=f"DEMO-B-{district_index:02d}",
                source_id=f"DEMO-HUB-{district_index:02d}",
                target_id=f"DEMO-HUB-{next_index:02d}",
                kind="backbone",
                is_demo=True,
            )
        )

    session.add_all(objects)
    session.add_all(channels)
    session.add_all(events)
    session.add_all(edges)
    session.flush()
    return {
        "objects": len(objects),
        "channels": len(channels),
        "events": len(events),
        "edges": len(edges),
    }


def main() -> None:
    with SessionLocal() as session:
        result = seed_geo_demo(session)
        session.commit()
    print(f"Demo Moscow network: {result}")


if __name__ == "__main__":
    main()
