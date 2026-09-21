import argparse
import time

from pipeline import config, extract, episodes as episodes_mod, candidates as candidates_mod
from pipeline import tags, features as features_mod, weather as weather_mod, splits, training, models


def resolve_sensor_type(name):
    resolved = config.SENSOR_ALIASES.get(name, name)
    if resolved not in config.DEVICE_TYPES:
        raise ValueError(f"unknown sensor type '{name}', expected one of {config.DEVICE_TYPES} or aliases {list(config.SENSOR_ALIASES)}")
    return resolved


def build_dataset(sensor_type, horizon_hours, with_neighbors=False, with_weather=False,
                   with_duty_cycle=False, exclude_period=None, exclude_triggers=None, force_extract=False):
    events = extract.extract_events(sensor_type, force=force_extract)
    episodes = episodes_mod.build_episodes(events)
    cand = candidates_mod.generate_candidates(events, sensor_type, exclude_triggers=exclude_triggers)
    numeric_mode = sensor_type in config.NUMERIC_DOMINANT_SENSOR_TYPES
    duty_cycle_mode = with_duty_cycle and sensor_type in config.DUTY_CYCLE_SENSOR_TYPES
    global_rates = features_mod.compute_global_rates(events, config.TRAIN_YEARS[1])
    feat = features_mod.compute_features(cand, events, episodes, numeric_mode=numeric_mode,
                                          duty_cycle_mode=duty_cycle_mode, global_rates=global_rates)
    feat = episodes_mod.assign_targets(feat, episodes, horizon_hours)

    if with_neighbors:
        events_tagged = tags.assign_groups(events)
        if "tag" not in feat.columns:
            feat = feat.merge(events[["channel_id", "tag"]].drop_duplicates("channel_id"), on="channel_id", how="left")
        feat_tagged = tags.assign_groups(feat)
        group_daily = tags.build_group_daily_features(events_tagged)
        feat = tags.attach_neighbor_features(feat_tagged, group_daily)

    if with_weather:
        wdf = weather_mod.fetch_weather()
        feat = weather_mod.attach_weather(feat, wdf)

    feat = splits.assign_split(feat, exclude_period=exclude_period)
    return feat, episodes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor-type", required=True)
    parser.add_argument("--horizon", type=int, default=config.DEFAULT_HORIZON_HOURS)
    parser.add_argument("--models", default="logistic_regression,hist_gradient_boosting,catboost,xgboost")
    parser.add_argument("--with-neighbors", action="store_true")
    parser.add_argument("--with-weather", action="store_true")
    parser.add_argument("--with-duty-cycle", action="store_true")
    parser.add_argument("--exclude-2021-storm", action="store_true")
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    sensor_type = resolve_sensor_type(args.sensor_type)
    if args.horizon <= 0:
        raise ValueError(f"--horizon must be positive, got {args.horizon}")
    model_names = args.models.split(",")
    unknown_models = [m for m in model_names if m not in models.MODEL_REGISTRY]
    if unknown_models:
        raise ValueError(f"unknown model(s) {unknown_models}, expected one of {list(models.MODEL_REGISTRY)}")
    exclude_period = ("2021-04-01", "2021-06-30") if args.exclude_2021_storm else None

    t0 = time.time()
    df, episodes = build_dataset(
        sensor_type, args.horizon,
        with_neighbors=args.with_neighbors, with_weather=args.with_weather,
        with_duty_cycle=args.with_duty_cycle,
        exclude_period=exclude_period, force_extract=args.force_extract,
    )
    cols = training.feature_columns(args.with_neighbors, args.with_weather, args.with_duty_cycle)
    results = training.run_models(df, cols, model_names)
    elapsed = time.time() - t0

    print(f"sensor_type={sensor_type} horizon={args.horizon}h n_rows={len(df)} n_positive={int(df['target'].sum())} elapsed={elapsed:.1f}s")
    print(results.to_string(index=False))

    if args.out:
        results.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
