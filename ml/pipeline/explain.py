import numpy as np
import pandas as pd

from pipeline.ensemble import ProbabilityBlend
from pipeline.models import CatBoostModel, LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel

LABELS = {
    "events_10m": "Событий за 10 мин",
    "events_1h": "Событий за 1 ч",
    "events_6h": "Событий за 6 ч",
    "events_24h": "Событий за 24 ч",
    "events_7d": "Событий за 7 сут",
    "events_30d": "Событий за 30 сут",
    "alarms_1h": "Тревог за 1 ч",
    "alarms_24h": "Тревог за 24 ч",
    "alarms_7d": "Тревог за 7 сут",
    "alarms_30d": "Тревог за 30 сут",
    "event_rate_delta": "Рост частоты событий",
    "rate_acceleration": "Ускорение частоты событий",
    "burst_count_24h": "Всплесков за 24 ч",
    "interarrival_mean": "Средний интервал между событиями",
    "interarrival_std": "Разброс интервалов между событиями",
    "interarrival_min": "Минимальный интервал между событиями",
    "interarrival_max": "Максимальный интервал между событиями",
    "ewma_event_rate_1d": "Сглаженная частота событий за сутки",
    "ewma_event_rate_7d": "Сглаженная частота событий за неделю",
    "ewma_alarm_rate_1d": "Сглаженная частота тревог за сутки",
    "ewma_alarm_rate_7d": "Сглаженная частота тревог за неделю",
    "state_entropy_200ev": "Разнообразие состояний",
    "n_unique_states_200ev": "Число разных состояний",
    "failures_1d": "Эпизодов за 1 сут",
    "failures_3d": "Эпизодов за 3 сут",
    "failures_7d": "Эпизодов за 7 сут",
    "failures_14d": "Эпизодов за 14 сут",
    "failures_30d": "Эпизодов за 30 сут",
    "failures_90d": "Эпизодов за 90 сут",
    "historical_failure_rate": "Частота эпизодов за всю историю",
    "median_time_between_failures_days": "Медианный интервал между эпизодами",
    "std_inter_failure_interval_days": "Разброс интервалов между эпизодами",
    "last_inter_failure_interval_days": "Последний интервал между эпизодами",
    "ratio_last_interval_to_historical_median": "Последний интервал к медианному",
    "time_since_last_failure_days": "Дней с последнего эпизода",
    "days_since_last_2nd_failure": "Дней со второго с конца эпизода",
    "days_since_last_3rd_failure": "Дней с третьего с конца эпизода",
    "time_since_last_event_hours": "Часов с последнего события",
    "channel_event_prior": "Типичная активность канала",
    "channel_alarm_prior": "Типичная частота тревог канала",
    "channel_failure_prior": "Типичная частота эпизодов канала",
    "ewma_failure_rate_7d": "Сглаженная частота эпизодов за неделю",
    "ewma_failure_rate_30d": "Сглаженная частота эпизодов за месяц",
    "weekday": "День недели",
    "hour": "Час суток",
    "month": "Месяц",
    "is_weekend": "Выходной день",
    "hour_sin": "Час суток",
    "hour_cos": "Час суток",
    "weekday_sin": "День недели",
    "weekday_cos": "День недели",
    "time_in_current_state_hours": "Часов в текущем состоянии",
    "mean_on_duration_hours": "Средняя длительность работы",
    "mean_off_duration_hours": "Средняя длительность простоя",
    "max_on_duration_hours": "Максимальная длительность работы",
    "max_off_duration_hours": "Максимальная длительность простоя",
    "transition_count_1h": "Переключений за 1 ч",
    "transition_count_6h": "Переключений за 6 ч",
    "transition_count_24h": "Переключений за 24 ч",
    "transition_count_7d": "Переключений за 7 сут",
    "on_off_cycles_1h": "Циклов включения за 1 ч",
    "on_off_cycles_6h": "Циклов включения за 6 ч",
    "on_off_cycles_24h": "Циклов включения за 24 ч",
    "on_off_cycles_7d": "Циклов включения за 7 сут",
    "sensor_code": "Тип датчика",
    "alarm_ch_prev_1h": "Тревог канала за 1 ч",
    "alarm_grp_prev_1h": "Тревог соседних каналов за 1 ч",
    "alarm_ch_prev_24h": "Тревог канала за 24 ч",
    "alarm_grp_prev_24h": "Тревог соседних каналов за 24 ч",
    "alarm_ch_prev_7d": "Тревог канала за 7 сут",
    "alarm_grp_prev_7d": "Тревог соседних каналов за 7 сут",
}


CALENDAR = {"weekday", "hour", "month", "is_weekend", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos"}


def contributions(model, features):
    if isinstance(model, ProbabilityBlend):
        linear = contributions(model.linear_model, features)
        tree = contributions(model.tree_model, features)
        return model.linear_weight * linear + (1.0 - model.linear_weight) * tree
    filled = features.fillna(-1)
    if isinstance(model, CatBoostModel):
        from catboost import Pool

        values = model.model.get_feature_importance(Pool(filled), type="ShapValues")[:, :-1]
    elif isinstance(model, LightGBMModel):
        values = model.model.predict(filled, pred_contrib=True)[:, :-1]
    elif isinstance(model, LogisticRegressionModel):
        values = model.scaler.transform(filled) * model.model.coef_[0]
    else:
        return None
    return pd.DataFrame(np.asarray(values, dtype=float), columns=features.columns, index=features.index)


def drivers(model, row, limit=3):
    contribution = contributions(model, row)
    if contribution is None:
        return []
    series = contribution.iloc[0].drop(labels=[name for name in CALENDAR if name in contribution.columns])
    by_label = series.groupby(lambda name: LABELS.get(name, name)).sum()
    top = by_label[by_label > 0].sort_values(ascending=False).head(limit)
    result = []
    for label, value in top.items():
        feature = max((name for name in series.index if LABELS.get(name, name) == label), key=lambda n: series[n])
        result.append({
            "feature": feature,
            "label": label,
            "value": float(row[feature].iloc[0]) if pd.notna(row[feature].iloc[0]) else None,
            "contribution": round(float(value), 4),
        })
    return result
