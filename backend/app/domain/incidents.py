"""Group channel-level predictions into incidents.

Channels at one location often react to one physical cause: a substation outage
de-energises every phase monitor behind it within seconds. Presenting each channel
as its own critical situation floods the dispatcher, so predictions that share a
scenario and a location group become one incident.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.schemas.predictions import Prediction, RiskLevel

# Incident scenario forecast by each device model (ТЗ, section 6).
SCENARIO_BY_DEVICE = {
    "pump": "flooding",
    "fan": "ventilation",
    "smoke": "fire",
    "phase": "power_loss",
    "power": "power_loss",
    "flood": "flooding",
}

SCENARIO_LABELS = {
    "flooding": "Подтопление",
    "ventilation": "Отказ вентиляции",
    "fire": "Пожар",
    "power_loss": "Потеря питания",
    "equipment": "Отказ оборудования",
}

# Tags look like "16-2.1.1.4.22.": object id, then the engineering-system tree.
# Three levels (object and two sections) keep one collector section together
# without merging unrelated systems of the same object.
LOCATION_LEVELS = 3

LEVEL_RANK: dict[RiskLevel, int] = {"critical": 0, "attention": 1, "observe": 2, "normal": 3}


def scenario_for(device_type: str, model_id: str = "") -> str:
    device = device_type or model_id.split("_", 1)[0]
    return SCENARIO_BY_DEVICE.get(device, "equipment")


def location_group(tag: str | None) -> str | None:
    if not tag:
        return None
    parts = [part for part in tag.strip().rstrip(".").split(".") if part]
    if not parts:
        return None
    return ".".join(parts[:LOCATION_LEVELS])


def location_label(group: str | None) -> str | None:
    if not group:
        return None
    obj, _, section = group.partition("-")
    return f"Объект {obj} · {section}" if section else f"Объект {obj}"


@dataclass
class Incident:
    key: str
    scenario: str
    location: str | None
    predictions: list[Prediction] = field(default_factory=list)

    @property
    def lead(self) -> Prediction:
        return self.predictions[0]

    @property
    def risk_level(self) -> RiskLevel:
        return self.lead.risk_level

    @property
    def asset_ids(self) -> list[str]:
        seen: dict[str, None] = {}
        for prediction in self.predictions:
            seen.setdefault(prediction.asset_id, None)
        return list(seen)

    @property
    def title(self) -> str:
        label = SCENARIO_LABELS.get(self.scenario, self.scenario)
        place = location_label(self.location) or self.lead.asset_id
        return f"{label} · {place}"


def _order(prediction: Prediction) -> tuple[int, float]:
    return (LEVEL_RANK[prediction.risk_level], -prediction.score)


def group_incidents(predictions: Iterable[Prediction]) -> list[Incident]:
    incidents: dict[str, Incident] = {}
    for prediction in predictions:
        scenario = prediction.scenario
        # Channels without a location tag cannot be grouped safely.
        group = prediction.location_group or f"asset:{prediction.asset_id}"
        key = f"{scenario}:{group}"
        incident = incidents.get(key)
        if incident is None:
            incident = Incident(key=key, scenario=scenario, location=prediction.location_group)
            incidents[key] = incident
        incident.predictions.append(prediction)
    result = list(incidents.values())
    for incident in result:
        incident.predictions.sort(key=_order)
    result.sort(key=lambda incident: _order(incident.lead))
    return result
