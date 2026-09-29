import os
import re

import pandas as pd

from pipeline import config

STATES_FILE = os.path.join(config.DATASET_DIR, "справочник_состояний.csv")
FAULT = "Неисправен"
EPOCH_ERROR = re.compile(r"^01\.01\.1970 ")
TIMESTAMP = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}$")
GAS_LIMITS = (0.0, 100.0)
GAS_ALARM = 1.0


def catalogue():
    if not os.path.exists(STATES_FILE):
        return pd.DataFrame(columns=["тип_датчика", "ид_набор_состояний", "название_состояния", "тревожное"])
    return pd.read_csv(STATES_FILE)


def alarm_states():
    table = catalogue()
    flags = table.groupby("название_состояния")["тревожное"].agg(lambda values: bool(values.astype(str).str.lower().eq("true").any()))
    return {state for state, alarm in flags.items() if alarm}


def normalize(values):
    values = pd.Series(values, copy=True).astype(str)
    return values.where(~values.str.match(EPOCH_ERROR), FAULT)


def gas_reading(values):
    numbers = pd.to_numeric(pd.Series(values).astype(str).str.replace(",", ".", regex=False), errors="coerce")
    invalid = numbers.notna() & ((numbers < GAS_LIMITS[0]) | (numbers > GAS_LIMITS[1]))
    alarm = (numbers >= GAS_ALARM) & ~invalid
    return numbers.mask(invalid), invalid.to_numpy(), alarm.to_numpy()


def is_timestamp(values):
    values = pd.Series(values).astype(str)
    return values.str.match(TIMESTAMP).to_numpy() & ~values.str.match(EPOCH_ERROR).to_numpy()


def summary(counts):
    counts = counts.assign(value=counts["value"].astype(str))
    epoch = counts["value"].str.match(EPOCH_ERROR)
    stamps = is_timestamp(counts["value"])
    named = counts.loc[counts["value"].isin(set(catalogue()["название_состояния"]))]
    agree = (named["alarm"] == "t") == named["value"].isin(alarm_states())
    total = int(counts["n"].sum())
    top = named.loc[~agree].groupby(["sensor_type", "value", "alarm"])["n"].sum().sort_values(ascending=False).head(10)
    return {
        "text_records": total,
        "known_state_share": round(float(named["n"].sum() / total), 4),
        "epoch_error_records": int(counts.loc[epoch, "n"].sum()),
        "timestamp_value_records": int(counts.loc[stamps, "n"].sum()),
        "alarm_flag_agreement": round(float(named.loc[agree, "n"].sum() / max(named["n"].sum(), 1)), 4),
        "largest_disagreements": [
            {"sensor_type": key[0], "state": key[1], "alarm_flag": key[2] == "t", "records": int(value)}
            for key, value in top.items()
        ],
    }
