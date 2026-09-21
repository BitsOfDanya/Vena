import numpy as np

from pipeline import config


def assign_split(df, exclude_period=None):
    year = df["ts"].dt.year
    split = np.select(
        [year <= config.TRAIN_YEARS[1], year == config.VALID_YEAR, year >= config.TEST_YEARS[0]],
        ["train", "valid", "test"], default="train",
    )
    df = df.copy()
    df["split"] = split
    if exclude_period is not None:
        start, end = exclude_period
        mask = (df["ts"] >= start) & (df["ts"] <= end)
        df = df.loc[~mask].reset_index(drop=True)
    return df
