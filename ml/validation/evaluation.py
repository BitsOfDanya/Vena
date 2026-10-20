"""Causal offline replay and episode-level scoring for frozen VENA models."""

import hashlib
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
from pipeline import artifacts, calibration, features
from pipeline.targets.discovery import state_episodes
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

TARGETS = {
    "pump_24h": "Неисправен",
    "pump_72h": "Неисправен",
    "flood_24h": "Затоплен",
    "phase_24h": "Обесточен",
}
EPISODE_COLUMNS = ["channel_id", "episode_start", "episode_end"]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_manifest(names):
    result = {}
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in result:
            continue
        _, meta, _ = load(name)
        result[name] = {
            "version": meta["version"],
            "training_period": meta["training_period"],
            "thresholds": meta["model_config"].get("risk_level_thresholds", {}),
            "files": {
                p.name: sha256(p)
                for p in sorted(Path(artifacts.artifact_dir(name)).glob("*"))
                if p.is_file()
            },
        }
        fallback = meta["model_config"].get("fallback_artifact")
        if fallback:
            pending.append(fallback)
    return result


@cache
def load(name):
    model, meta = artifacts.load_artifact(name)
    return model, meta, artifacts.load_calibrator(name)


def prefix_ewma(times, event_times, weights, half_life):
    """Match production inference on a truncated history, including silent days.

    The legacy batch helper extends the daily series to its last future event.
    Clip separately at each query's last observed event so future silence/events
    cannot alter an earlier score. No production feature code is modified.
    """
    query = times.astype("datetime64[s]").astype(np.int64)
    seconds = event_times.astype("datetime64[s]").astype(np.int64)
    if not len(seconds):
        return np.zeros(len(query))
    days = seconds // 86400
    daily = np.bincount(days - days[0], weights=weights)
    smoothed = pd.Series(daily).ewm(halflife=half_life, adjust=False).mean().to_numpy()
    counts = np.searchsorted(seconds, query, side="right")
    last_day = days[np.maximum(counts - 1, 0)]
    index = np.minimum(query // 86400 - 1, last_day) - days[0]
    return np.where(
        (counts > 0) & (index >= 0), smoothed[np.clip(index, 0, len(smoothed) - 1)], 0.0
    )


def causal_features(times, events, observed_episodes, cfg):
    ev = events.sort_values("ts", kind="stable")
    starts = np.sort(observed_episodes.episode_start.to_numpy(dtype="datetime64[ns]"))
    times = np.asarray(times, dtype="datetime64[ns]")
    ev_times = ev.ts.to_numpy(dtype="datetime64[ns]")
    frame = features.compute_features_single(
        times,
        ev_times,
        ev.alarm_flag.to_numpy(),
        ev.raw_value.to_numpy(),
        starts,
        numeric_mode=cfg.get("numeric_mode", False),
        duty_cycle_mode=cfg.get("duty_cycle_mode", False),
        global_rates=cfg.get("global_rates"),
    )
    for kind, stamps, weights, halves in [
        ("event", ev_times, np.ones(len(ev)), (1, 7)),
        ("alarm", ev_times, ev.alarm_flag.to_numpy(), (1, 7)),
        ("failure", starts, np.ones(len(starts)), (7, 30)),
    ]:
        for half in halves:
            frame[f"ewma_{kind}_rate_{half}d"] = prefix_ewma(
                times, stamps, weights, half
            )
    return frame


def score_channel(events, truth, name, start, end, frequency="6h"):
    """Truth is used exclusively after scoring, never to construct features.

    end is the last instant with known outcomes. Incomplete forecast horizons
    and instants inside a known active physical episode are excluded.
    """
    events = events.sort_values("ts", kind="stable").reset_index(drop=True)
    if events.empty or events.channel_id.nunique() != 1:
        raise ValueError("Expected a nonempty single-channel event stream")
    if not events.alarm_flag.isin([0, 1]).all():
        raise ValueError("alarm_flag must be 0/1")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start < events.ts.min() or start >= end:
        raise ValueError("Invalid evaluation period or missing warm-up history")
    _, primary_meta, _ = load(name)
    horizon = int(primary_meta["model_config"]["horizon_hours"])
    times = pd.date_range(start, end - pd.Timedelta(hours=horizon), freq=frequency)
    if not len(times):
        raise ValueError("No complete forecast horizons")
    channel = str(events.channel_id.iloc[0])
    truth = truth.loc[truth.channel_id.astype(str) == channel].copy()
    observed = state_episodes(events, TARGETS[name])
    cfg = primary_meta["model_config"]
    fallback = cfg.get("fallback_artifact")
    variants = np.full(len(times), name, dtype=object)
    if fallback:
        variants[
            (times - events.ts.min()) < pd.Timedelta(days=cfg["min_history_days"])
        ] = fallback
    raw, probability, threshold, baseline = [np.zeros(len(times)) for _ in range(4)]
    for variant in np.unique(variants):
        mask = variants == variant
        model, meta, calibrator = load(variant)
        frame = causal_features(times[mask], events, observed, meta["model_config"])
        values = frame[meta["feature_columns"]]
        raw[mask] = model.predict_proba(values)
        probability[mask] = (
            np.clip(calibration.apply_isotonic(calibrator, raw[mask]), 0.001, 0.99)
            if calibrator is not None
            else raw[mask]
        )
        threshold[mask] = meta["model_config"]["risk_level_thresholds"]["high"]
        baseline[mask] = frame.failures_7d.to_numpy()
    if not np.isfinite(raw).all() or not np.isfinite(probability).all():
        raise ValueError("Nonfinite predictions")
    starts = np.sort(truth.episode_start.to_numpy(dtype="datetime64[ns]"))
    t = times.to_numpy()
    target = np.searchsorted(
        starts, t + np.timedelta64(horizon, "h"), side="right"
    ) > np.searchsorted(starts, t, side="right")
    active = np.zeros(len(t), dtype=bool)
    for row in truth.itertuples():
        active |= (times >= row.episode_start) & (times <= row.episode_end)
    result = pd.DataFrame(
        {
            "channel_id": channel,
            "ts": times,
            "model": name,
            "variant": variants,
            "raw_score": raw,
            "probability": probability,
            "threshold_high": threshold,
            "alert": raw >= threshold,
            "baseline_score": baseline,
            "baseline_alert": baseline > 0,
            "target": target.astype(int),
            "active_episode": active,
            "horizon_hours": horizon,
        }
    )
    result["eligible"] = ~active
    return result


def alert_metrics(rows, truth, alert_column="alert", cooldown_hours=24):
    eligible = rows.loc[rows.eligible].sort_values("ts")
    alerts = []
    for channel, group in eligible.loc[eligible[alert_column]].groupby("channel_id"):
        last = None
        for row in group.itertuples():
            if last is None or row.ts - last >= pd.Timedelta(hours=cooldown_hours):
                alerts.append(row)
                last = row.ts
    covered, lead, assessable = 0, [], 0
    for episode in truth.itertuples():
        history = eligible.loc[eligible.channel_id == str(episode.channel_id)]
        if history.empty:
            continue
        horizon = pd.Timedelta(hours=int(history.horizon_hours.iloc[0]))
        # Require a complete pre-event window; do not count left/right-censored episodes.
        if (
            episode.episode_start - horizon < history.ts.min()
            or episode.episode_start > history.ts.max() + horizon
        ):
            continue
        assessable += 1
        hits = [
            a.ts
            for a in alerts
            if a.channel_id == str(episode.channel_id)
            and episode.episode_start - horizon <= a.ts < episode.episode_start
        ]
        if hits:
            covered += 1
            lead.append((episode.episode_start - min(hits)).total_seconds() / 3600)
    correct = sum(int(a.target) for a in alerts)
    return {
        "alerts": len(alerts),
        "true_alerts": correct,
        "false_alerts": len(alerts) - correct,
        "precision": correct / len(alerts) if alerts else None,
        "episodes": assessable,
        "covered_episodes": covered,
        "episode_recall": covered / assessable if assessable else None,
        "median_lead_hours": float(np.median(lead)) if lead else None,
    }


def summarize(rows, truth):
    data = rows.loc[rows.eligible]
    if data.empty:
        return {"status": "no_eligible_predictions"}
    y = data.target.to_numpy()
    has_both = len(np.unique(y)) == 2
    ap = float(average_precision_score(y, data.raw_score)) if y.sum() else None
    base = float(y.mean())
    operations = alert_metrics(rows, truth)
    # Fixed schedule; excluded active-episode intervals are not at-risk exposure.
    hours = sum(
        (g.ts.sort_values().diff().dropna().median() / pd.Timedelta(hours=1))
        * len(g.loc[g.eligible])
        for _, g in rows.groupby("channel_id")
        if len(g) > 1
    )
    operations["false_alerts_per_channel_day"] = (
        operations["false_alerts"] / (hours / 24) if hours else None
    )
    return {
        "predictions": len(data),
        "excluded_active_predictions": int((~rows.eligible).sum()),
        "channels": int(data.channel_id.nunique()),
        "positive_rate": base,
        "ap": ap,
        "ap_lift": ap / base if ap is not None and base else None,
        "roc_auc": float(roc_auc_score(y, data.raw_score)) if has_both else None,
        "brier": float(brier_score_loss(y, data.probability)),
        "mean_probability": float(data.probability.mean()),
        "maximum_raw_score": float(data.raw_score.max()),
        "threshold_high_range": [
            float(data.threshold_high.min()),
            float(data.threshold_high.max()),
        ],
        "recent_fault_baseline_ap": float(
            average_precision_score(y, data.baseline_score)
        )
        if y.sum()
        else None,
        "operations": operations,
        "recent_fault_baseline_operations": alert_metrics(
            rows, truth, "baseline_alert"
        ),
    }
