"""Explicit, fixed MetroPT -> one compressor event channel adapter.

This measures domain transfer, not pump accuracy in Moscow. No labels are
injected into the input. DV_eletric=1 means compressor under load. LPS and
Oil_level are directly observed alarm bits. Fault truth comes from UCI reports.
"""

import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from validation.evaluation import EPISODE_COLUMNS, sha256

SOURCE = "https://archive.ics.uci.edu/dataset/791/metropt+3+dataset"
DOWNLOAD = "https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip"
FAILURES = [
    ("2020-04-18 00:00", "2020-04-18 23:59"),
    ("2020-05-29 23:30", "2020-05-30 06:00"),
    ("2020-06-05 10:00", "2020-06-07 14:30"),
    ("2020-07-15 14:30", "2020-07-15 19:00"),
]


def prepare(directory):
    directory = Path(directory)
    path = directory / "MetroPT3(AirCompressor).csv"
    if not path.exists() and (directory / "source.zip").exists():
        with zipfile.ZipFile(directory / "source.zip") as archive:
            member = next(n for n in archive.namelist() if Path(n).name == path.name)
            # Copy the known member, never extract arbitrary archive paths.
            with archive.open(member) as src, path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    if not path.exists():
        raise FileNotFoundError(f"Download {DOWNLOAD} to {directory / 'source.zip'}")
    frame = pd.read_csv(
        path,
        usecols=["timestamp", "DV_eletric", "LPS", "Oil_level"],
        parse_dates=["timestamp"],
    ).sort_values("timestamp", kind="stable")
    if frame.isna().any().any():
        raise ValueError(
            "Missing input values; adapter needs an explicit missingness policy"
        )
    # Combine observable status into one equipment channel; a compressor is not
    # fourteen independent failures just because it has fourteen sensors.
    alarm = (frame.LPS > 0.5) | (frame.Oil_level > 0.5)
    value = np.where(
        frame.Oil_level > 0.5,
        "Низкий уровень масла",
        np.where(
            frame.LPS > 0.5,
            "Низкое давление",
            np.where(frame.DV_eletric > 0.5, "Включен", "Выключен"),
        ),
    )
    values = pd.Series(value, index=frame.index)
    changed = values.ne(values.shift())
    events = pd.DataFrame(
        {
            "channel_id": "metropt3/APU",
            "ts": frame.loc[changed, "timestamp"],
            "raw_value": values.loc[changed],
            "alarm_flag": alarm.loc[changed].astype(int),
        }
    )
    truth = pd.DataFrame(
        [("metropt3/APU", pd.Timestamp(a), pd.Timestamp(b)) for a, b in FAILURES],
        columns=EPISODE_COLUMNS,
    )
    return (
        events.reset_index(drop=True),
        truth,
        {
            "source": SOURCE,
            "download": DOWNLOAD,
            "license": "CC BY 4.0",
            "citation": "Davari, Veloso, Ribeiro & Gama (2021), MetroPT-3, DOI 10.24432/C5VW3R",
            "sha256": sha256(path),
            "raw_rows": len(frame),
            "events": len(events),
            "data_start": frame.timestamp.min().isoformat(),
            "data_end": frame.timestamp.max().isoformat(),
            "evaluation_start": "2020-04-01",
            "evaluation_end": "2020-08-01",
            "adapter": "DV_eletric load/unload; LPS low-pressure; Oil_level low-oil; changed combined state only",
            "truth": "Four compressor leak reports, not sensor-generated labels",
            "limitations": [
                "Single compressor, four failures: no population confidence interval",
                "Already explored historically; this is a frozen-model transfer diagnostic, not a fresh lockbox",
                "Different equipment and event semantics; probabilities may not transfer",
                "No observed Неисправен state: production failure-history features remain at their cold-start values",
                "Report end timestamps used as given; exact return-to-service times are not independently verified",
            ],
        },
    )
