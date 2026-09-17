import time
import pandas as pd

from pipeline import config, extract, episodes as episodes_mod, candidates as candidates_mod
from pipeline import tags, features as features_mod, weather as weather_mod, splits, training, models as models_mod, evaluate


class DeviceContext:
    def __init__(self, sensor_type, exclude_triggers=None):
        self.sensor_type = sensor_type
        self.events = extract.extract_events(sensor_type)
        self.episodes = episodes_mod.build_episodes(self.events)
        self.candidates = candidates_mod.generate_candidates(self.events, sensor_type, exclude_triggers=exclude_triggers)
        numeric_mode = sensor_type in config.NUMERIC_DOMINANT_SENSOR_TYPES
        duty_cycle_mode = sensor_type in config.DUTY_CYCLE_SENSOR_TYPES
        self.global_rates = features_mod.compute_global_rates(self.events, config.TRAIN_YEARS[1])
        self.features_base = features_mod.compute_features(
            self.candidates, self.events, self.episodes, numeric_mode=numeric_mode,
            duty_cycle_mode=duty_cycle_mode, global_rates=self.global_rates,
        )
        self.duty_cycle_mode = duty_cycle_mode
        self._neighbor_cache = None
        self._weather_cache = None

    def with_neighbors(self, df):
        if self._neighbor_cache is None:
            events_tagged = tags.assign_groups(self.events)
            group_daily = tags.build_group_daily_features(events_tagged)
            self._neighbor_cache = (events_tagged, group_daily)
        _, group_daily = self._neighbor_cache
        if "tag" not in df.columns:
            df = df.merge(self.events[["channel_id", "tag"]].drop_duplicates("channel_id"), on="channel_id", how="left")
        df = tags.assign_groups(df)
        return tags.attach_neighbor_features(df, group_daily)

    def with_weather(self, df):
        if self._weather_cache is None:
            self._weather_cache = weather_mod.fetch_weather()
        return weather_mod.attach_weather(df, self._weather_cache)

    def build(self, horizon_hours=24, with_neighbors=False, with_weather=False, exclude_period=None):
        df = episodes_mod.assign_targets(self.features_base, self.episodes, horizon_hours)
        if with_neighbors:
            df = self.with_neighbors(df)
        if with_weather:
            df = self.with_weather(df)
        df = splits.assign_split(df, exclude_period=exclude_period)
        return df


def device_comparison(model_names, out_path, sensor_types=None):
    rows = []
    for sensor_type in (sensor_types or config.DEVICE_TYPES):
        t0 = time.time()
        ctx = DeviceContext(sensor_type)
        df = ctx.build(horizon_hours=24)
        cols = training.feature_columns()
        n_channels = ctx.events["channel_id"].nunique()
        n_episodes = len(ctx.episodes)
        res = training.run_models(df, cols, model_names)
        res["sensor_type"] = sensor_type
        res["n_channels"] = n_channels
        res["n_episodes"] = n_episodes
        res["n_candidates"] = len(df)
        res["elapsed_sec"] = round(time.time() - t0, 1)
        rows.append(res)
        print(sensor_type, "done in", round(time.time() - t0, 1), "s, n_candidates=", len(df), "n_episodes=", n_episodes)

    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def horizon_comparison(sensor_types, model_names, out_path):
    rows = []
    for sensor_type in sensor_types:
        ctx = DeviceContext(sensor_type)
        for horizon in config.HORIZONS_HOURS:
            df = ctx.build(horizon_hours=horizon)
            cols = training.feature_columns()
            res = training.run_models(df, cols, model_names)
            res["sensor_type"] = sensor_type
            res["horizon_hours"] = horizon
            rows.append(res)
            print(sensor_type, horizon, "done")
    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def storm_2021_ablation(sensor_type, model_names, out_path):
    ctx = DeviceContext(sensor_type)
    rows = []
    for label, exclude in [("with_2021_storm", None), ("without_2021_storm", ("2021-04-01", "2021-06-30"))]:
        df = ctx.build(horizon_hours=24, exclude_period=exclude)
        cols = training.feature_columns()
        res = training.run_models(df, cols, model_names)
        res["variant"] = label
        rows.append(res)
    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def weather_ablation(sensor_type, model_names, out_path):
    ctx = DeviceContext(sensor_type)
    rows = []
    for label, with_weather in [("without_weather", False), ("with_weather", True)]:
        df = ctx.build(horizon_hours=24, with_weather=with_weather)
        cols = training.feature_columns(with_weather=with_weather)
        res = training.run_models(df, cols, model_names)
        res["variant"] = label
        rows.append(res)
    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def neighbor_ablation(sensor_type, model_names, out_path):
    ctx = DeviceContext(sensor_type)
    rows = []
    for label, with_neighbors in [("without_neighbors", False), ("with_neighbors", True)]:
        df = ctx.build(horizon_hours=24, with_neighbors=with_neighbors)
        cols = training.feature_columns(with_neighbors=with_neighbors)
        res = training.run_models(df, cols, model_names)
        res["variant"] = label
        rows.append(res)
    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def _eval_row(model, eval_df, cols, tag):
    if eval_df.empty or eval_df["target"].sum() == 0:
        return None
    score = model.predict_proba(eval_df[cols])
    m = evaluate.evaluate(eval_df["target"].values, score)
    m.update(evaluate.evaluate_daily_topk(eval_df["ts"].values, eval_df["target"].values, score))
    m.update(tag)
    return m


def _chronic_flag_by_row(df, episodes):
    return (df["failures_90d"] >= config.CHRONIC_MIN_HISTORICAL_FAILURES).astype(int)


def _chronic_flag_by_channel_quantile(df, episodes, quantile=0.5):
    train_episodes = episodes[episodes["episode_start"].dt.year <= config.TRAIN_YEARS[1]]
    channel_counts = train_episodes.groupby("channel_id", observed=True).size()
    if channel_counts.empty:
        return pd.Series(0, index=df.index, dtype=int)
    threshold = channel_counts.quantile(quantile)
    chronic_channels = set(channel_counts[channel_counts >= threshold].index)
    return df["channel_id"].isin(chronic_channels).astype(int)


def _run_chronic_variants(df, model_names, out_path):
    cols_base = training.feature_columns()
    cols_flag = cols_base + ["is_chronic"]
    train_all = df[df["split"] == "train"]

    rows = []
    for model_name in model_names:
        model_global = models_mod.MODEL_REGISTRY[model_name]()
        model_global.fit(train_all[cols_base], train_all["target"])

        model_flag = models_mod.MODEL_REGISTRY[model_name]()
        model_flag.fit(train_all[cols_flag], train_all["target"])

        segment_models = {}
        segment_train_rows = {}
        for segment_value in [1, 0]:
            train_seg = train_all[train_all["is_chronic"] == segment_value]
            segment_train_rows[segment_value] = len(train_seg)
            if len(train_seg) >= 200 and train_seg["target"].sum() >= 20:
                seg_model = models_mod.MODEL_REGISTRY[model_name]()
                seg_model.fit(train_seg[cols_base], train_seg["target"])
                segment_models[segment_value] = seg_model

        for split_name in ["valid", "test"]:
            split_all = df[df["split"] == split_name]
            for segment_label, segment_value in [("all", None), ("chronic", 1), ("non_chronic", 0)]:
                eval_df = split_all if segment_value is None else split_all[split_all["is_chronic"] == segment_value]
                base_tag = {"model": model_name, "split": split_name, "segment": segment_label,
                            "n_train_rows": len(train_all)}

                m = _eval_row(model_global, eval_df, cols_base, {**base_tag, "variant": "global_model"})
                if m:
                    rows.append(m)

                m2 = _eval_row(model_flag, eval_df, cols_flag, {**base_tag, "variant": "global_model_plus_chronic_flag"})
                if m2:
                    rows.append(m2)

                if segment_value in segment_models:
                    seg_tag = {**base_tag, "variant": "separate_chronic_model",
                               "n_train_rows": segment_train_rows[segment_value]}
                    m3 = _eval_row(segment_models[segment_value], eval_df, cols_base, seg_tag)
                    if m3:
                        rows.append(m3)

    result = pd.DataFrame(rows)
    result.to_csv(out_path, index=False)
    return result


def chronic_channel_comparison(sensor_type, model_names, out_path, horizon_hours=24):
    ctx = DeviceContext(sensor_type)
    df = ctx.build(horizon_hours=horizon_hours).copy()
    df["is_chronic"] = _chronic_flag_by_row(df, ctx.episodes)
    return _run_chronic_variants(df, model_names, out_path)


def chronic_channel_comparison_by_quantile(sensor_type, model_names, out_path, quantile=0.5, horizon_hours=24):
    ctx = DeviceContext(sensor_type)
    df = ctx.build(horizon_hours=horizon_hours).copy()
    df["is_chronic"] = _chronic_flag_by_channel_quantile(df, ctx.episodes, quantile=quantile)
    return _run_chronic_variants(df, model_names, out_path)


def duty_cycle_ablation(sensor_type, model_names, out_path):
    ctx = DeviceContext(sensor_type)
    rows = []
    for label, with_duty_cycle in [("without_duty_cycle", False), ("with_duty_cycle", True)]:
        df = ctx.build(horizon_hours=24)
        cols = training.feature_columns(with_duty_cycle=with_duty_cycle)
        res = training.run_models(df, cols, model_names)
        res["variant"] = label
        rows.append(res)
    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def candidate_trigger_ablation(sensor_type, model_names, out_path, horizon_hours=24):
    from pipeline import alerts as alerts_mod
    rows = []
    for exclude in [None] + list(candidates_mod.TRIGGER_TYPES):
        label = "all" if exclude is None else f"minus_{exclude}"
        excl = None if exclude is None else [exclude]
        ctx = DeviceContext(sensor_type, exclude_triggers=excl)
        df = ctx.build(horizon_hours=horizon_hours)
        test_df = df[df["split"] == "test"]
        test_episodes = ctx.episodes[
            (ctx.episodes["episode_start"].dt.year >= config.TEST_YEARS[0])
        ]
        n_days = max((test_df["ts"].max() - test_df["ts"].min()).total_seconds() / 86400.0, 1.0) if len(test_df) else 1.0
        coverage = alerts_mod.candidate_coverage(test_df[["channel_id", "ts"]], test_episodes, horizon_hours)
        cols = training.feature_columns(with_duty_cycle=ctx.duty_cycle_mode)
        model_res = training.run_models(df, cols, model_names)
        model_res = model_res[model_res["split"] == "test"]
        model_res["trigger_variant"] = label
        model_res["candidates_per_day"] = len(df) / n_days
        model_res["candidate_coverage"] = coverage.mean() if len(coverage) else None
        model_res["n_episodes_in_test"] = len(test_episodes)
        model_res["positive_rate"] = df["target"].mean()
        rows.append(model_res)
        print(sensor_type, label, "done, coverage=", round(coverage.mean(), 4) if len(coverage) else None)
    rows = [r for r in rows if not r.empty]
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def rolling_backtest_device(sensor_type, model_names, out_path, horizon_hours=24,
                             with_neighbors=False, with_duty_cycle=False, exclude_triggers=None, ctx=None):
    from pipeline import backtest
    ctx = ctx or DeviceContext(sensor_type, exclude_triggers=exclude_triggers)
    df = ctx.build(horizon_hours=horizon_hours, with_neighbors=with_neighbors)
    cols = training.feature_columns(with_neighbors=with_neighbors, with_duty_cycle=with_duty_cycle)
    results = backtest.run_rolling_backtest(df, cols, model_names)
    results["sensor_type"] = sensor_type
    results["horizon_hours"] = horizon_hours
    results.to_csv(out_path, index=False)
    agg = backtest.aggregate_backtest(results)
    agg.to_csv(out_path.replace(".csv", "_agg.csv"), index=False)
    return results, agg


def chronic_quantile_rolling_check(sensor_type, model_names, out_path, quantiles=None, horizon_hours=24):
    from pipeline import backtest
    quantiles = quantiles or config.CHRONIC_QUANTILE_OPTIONS
    ctx = DeviceContext(sensor_type)
    df = ctx.build(horizon_hours=horizon_hours)
    cols = training.feature_columns()
    rows = []
    for q in quantiles:
        flagged = df.copy()
        flagged["is_chronic"] = _chronic_flag_by_channel_quantile(flagged, ctx.episodes, quantile=q)
        for segment_label, segment_value in [("chronic", 1), ("non_chronic", 0)]:
            seg = flagged[flagged["is_chronic"] == segment_value]
            if seg.empty:
                continue
            res = backtest.run_rolling_backtest(seg, cols, model_names)
            if res.empty:
                continue
            res["quantile"] = q
            res["segment"] = segment_label
            res["n_rows"] = len(seg)
            rows.append(res)
    result = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result.to_csv(out_path, index=False)
    return result


def hyperparameter_search(sensor_type, param_grid, out_path, horizon_hours=24, model_name="catboost"):
    from pipeline import backtest
    ctx = DeviceContext(sensor_type)
    df = ctx.build(horizon_hours=horizon_hours)
    cols = training.feature_columns()
    rows = []
    for i, params in enumerate(param_grid):
        for fold in config.ROLLING_FOLDS:
            fdf = backtest.assign_fold(df, fold)
            train = fdf[fdf["fold_split"] == "train"]
            valid = fdf[fdf["fold_split"] == "valid"]
            if valid.empty or valid["target"].sum() == 0 or train.empty:
                continue
            model = models_mod.MODEL_REGISTRY[model_name](params=params)
            model.fit(train[cols], train["target"])
            score = model.predict_proba(valid[cols])
            m = evaluate.evaluate(valid["target"].values, score)
            m.update(evaluate.evaluate_daily_topk(valid["ts"].values, valid["target"].values, score))
            m["params_id"] = i
            m["params"] = str(params)
            m["fold"] = fold["name"]
            rows.append(m)
    result = pd.DataFrame(rows)
    result.to_csv(out_path, index=False)
    return result
