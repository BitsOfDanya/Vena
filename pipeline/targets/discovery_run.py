import os
import sys

import pandas as pd

from pipeline import config, extract
from pipeline.targets import discovery

BULK_OBSERVATION_STATES = {"Движения нет", "Обнаружено движение"}
MIN_STATE_EVENTS = 30
BASE_RATE_HORIZONS = (24, 72)


def load_literal_events(con, sensor_type, exclude_states=()):
    excl = ""
    if exclude_states:
        excl = " AND e.значение_датчика NOT IN (" + ",".join(f"'{s}'" for s in exclude_states) + ")"
    df = con.execute(f"""
        SELECT e.ид_канала_данных AS channel_id,
               strptime(e.дата || ' ' || e.время, '%Y-%m-%d %H:%M:%S') AS ts,
               e.тревожное AS alarm_flag, e.значение_датчика AS raw_value
        FROM events_all e JOIN channels c ON c.ид_канала_данных = e.ид_канала_данных
        WHERE c.тип_датчика = ? AND TRY_CAST(e.значение_датчика AS DOUBLE) IS NULL{excl}
    """, [sensor_type]).df()
    df["alarm_flag"] = (df["alarm_flag"] == "t").astype("int8")
    return df


def sensor_types(con):
    return con.execute("SELECT DISTINCT тип_датчика FROM channels ORDER BY 1").df().iloc[:, 0].tolist()


def build(out_dir):
    con = extract._connect()
    extract._build_views(con)
    n_channels = con.execute(
        "SELECT тип_датчика, COUNT(*) FROM channels GROUP BY 1").df().set_index("тип_датчика").iloc[:, 0].to_dict()
    rows, trans = [], []
    for st in sensor_types(con):
        exclude = BULK_OBSERVATION_STATES if st in ("Датчик движения", "КД Дверь") else ()
        ev = load_literal_events(con, st, exclude)
        if ev.empty:
            continue
        ev = ev.sort_values(["channel_id", "ts"]).reset_index(drop=True)
        t_tr = discovery.transition_counts(ev, min_count=20)
        t_tr.insert(0, "sensor_type", st)
        trans.append(t_tr)
        counts = ev["raw_value"].value_counts()
        for state, n_ev in counts.items():
            if n_ev < MIN_STATE_EVENTS:
                continue
            eps = discovery.state_episodes(ev, state)
            row = {"sensor_type": st, "state": state, "n_channels_of_type": int(n_channels.get(st, 0)),
                   "n_events": int(n_ev), "n_channels_with_events": int(ev.loc[ev.raw_value == state, "channel_id"].nunique())}
            row.update(discovery.episode_summary(eps))
            for h in BASE_RATE_HORIZONS:
                row[f"base_rate_{h}h"] = discovery.horizon_base_rate(ev, eps, h)
            row["alarm_flag_rate"] = float(ev.loc[ev.raw_value == state, "alarm_flag"].mean())
            rows.append(row)
        print(st, len(ev), flush=True)
    matrix = pd.DataFrame(rows)
    os.makedirs(out_dir, exist_ok=True)
    matrix.to_csv(os.path.join(out_dir, "target_discovery_matrix.csv"), index=False)
    pd.concat(trans, ignore_index=True).to_csv(os.path.join(out_dir, "target_discovery_transitions.csv"), index=False)
    return matrix


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else config.TABLES_DIR)
