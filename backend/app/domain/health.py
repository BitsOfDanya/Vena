"""Health index of a location: one number 0-100 from all 24-hour forecasts.

For each scenario the location risk is the highest calibrated probability among
its channels; for power loss the location model's probability is used when it
is higher. Scenarios are combined as independent: risk = 1 - prod(1 - risk_s). Combining
many channels overstates the risk of large locations, so the combined risk is
mapped to the observed frequency with the calibration points in
ml/configs/health_index.json (daily cuts of 2025, see ml/run_health_index.py).
The index is 100 * (1 - calibrated risk): 100 means no expected event within 24 h.
"""

import json
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.incidents import location_label
from app.schemas.predictions import Prediction

HORIZON_HOURS = 24


@dataclass
class LocationHealth:
    group: str
    label: str | None
    index: int
    risk_by_scenario: dict[str, float] = field(default_factory=dict)
    channels: int = 0

    @property
    def main_scenario(self) -> str | None:
        if not self.risk_by_scenario:
            return None
        return max(self.risk_by_scenario, key=lambda key: self.risk_by_scenario[key])


Points = tuple[list[float], list[float]]


def load_calibration(ml_dir: Path) -> Points | None:
    path = ml_dir / "configs" / "health_index.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return list(data["raw_risk"]), list(data["risk"])


def calibrate(raw: float, points: Points | None) -> float:
    """Linear interpolation between isotonic points, clipped at the ends."""
    if points is None:
        return raw
    xs, ys = points
    if raw <= xs[0]:
        return ys[0]
    if raw >= xs[-1]:
        return ys[-1]
    right = bisect_right(xs, raw)
    x0, x1, y0, y1 = xs[right - 1], xs[right], ys[right - 1], ys[right]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (raw - x0) / (x1 - x0)


def location_health(
    predictions: list[Prediction],
    incident_probability: dict[tuple[str, str], float],
    points: Points | None = None,
) -> dict[str, LocationHealth]:
    risks: dict[str, dict[str, float]] = {}
    channels: dict[str, set[str]] = {}
    for prediction in predictions:
        group = prediction.location_group
        if group is None or prediction.horizon_hours != HORIZON_HOURS:
            continue
        if prediction.score_type != "calibrated_probability":
            continue
        scenario_risk = risks.setdefault(group, {})
        scenario_risk[prediction.scenario] = max(
            scenario_risk.get(prediction.scenario, 0.0), prediction.score
        )
        channels.setdefault(group, set()).add(prediction.asset_id)
    result = {}
    for group, scenario_risk in risks.items():
        for (scenario, location), probability in incident_probability.items():
            if location == group and scenario in scenario_risk:
                scenario_risk[scenario] = max(scenario_risk[scenario], probability)
        survive = 1.0
        for risk in scenario_risk.values():
            survive *= 1.0 - risk
        result[group] = LocationHealth(
            group=group,
            label=location_label(group),
            index=round(100 * (1 - calibrate(1 - survive, points))),
            risk_by_scenario={key: round(value, 4) for key, value in scenario_risk.items()},
            channels=len(channels[group]),
        )
    return result
