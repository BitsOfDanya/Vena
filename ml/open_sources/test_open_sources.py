import zipfile

import numpy as np
import pandas as pd
import pytest

from open_sources.download import digest, fetch_file, safe_extract
from open_sources.experiments import (
    binary_metrics,
    metro_analog_features,
    smoke_file,
    split_groups,
)


def test_download_rejects_a_cached_file_with_wrong_published_checksum(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("broken")
    with pytest.raises(ValueError, match="MD5"):
        fetch_file("https://unused.example", path, expected_md5="0" * 32)


def test_extraction_rejects_traversal_before_writing_anything(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("fine.txt", "data")
        handle.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError, match="Unsafe"):
        safe_extract(archive, tmp_path / "raw")
    assert not (tmp_path / "raw" / "fine.txt").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_local_download_and_reuse(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1,2\n")
    dest = tmp_path / "nested" / "download.csv"
    expected = digest(source, "md5")
    first = fetch_file(source.as_uri(), dest, expected)
    second = fetch_file("https://unreachable.example", dest, expected)
    assert first["sha256"] == second["sha256"] == digest(source)


def test_group_split_never_splits_experiments_or_operating_conditions():
    groups = np.repeat([f"model{i}" for i in range(12)], 15)
    train, test = split_groups(groups)
    assert set(groups[train]).isdisjoint(set(groups[test]))
    assert len(train) + len(test) == len(groups)


def test_metro_features_are_unchanged_by_future_values():
    times = pd.date_range("2020-02-01", periods=20 * 60, freq="1min")
    frame = pd.DataFrame({"timestamp": times})
    for column in [
        "TP2",
        "TP3",
        "H1",
        "DV_pressure",
        "Reservoirs",
        "Motor_current",
        "Oil_temperature",
    ]:
        frame[column] = np.sin(np.arange(len(frame)) / 100)
    cutoff = pd.Timestamp("2020-02-01 12:00")
    full = metro_analog_features(frame).loc[cutoff]
    prefix = metro_analog_features(frame.loc[frame.timestamp <= cutoff]).loc[cutoff]
    np.testing.assert_allclose(full, prefix)
    frame.loc[frame.timestamp > cutoff, "TP2"] = 1e9
    np.testing.assert_allclose(full, metro_analog_features(frame).loc[cutoff])


def write_smoke(path, onset):
    lines = ["date", "", "Counter\tAlarm?\tObscuration (%/ft)\tMIC(pA)\tCO\tMicrophone"]
    lines += [
        f"{s}\t{int(s >= onset)}\t{s / 100}\t{100 - s / 10}\t0.01\t1"
        for s in range(101)
    ]
    path.write_text("\n".join(lines))


def test_nist_targets_are_future_only_and_alarm_channels_never_become_features(
    tmp_path,
):
    path = tmp_path / "P01-A-001.tsv"
    write_smoke(path, 60)
    early = smoke_file(path)
    assert early.second.min() >= 10 and early.second.max() < 60
    assert early.loc[early.target == 1, "second"].tolist() == [50, 55]
    assert "Alarm?" not in early and "Microphone" not in early
    write_smoke(path, 80)
    later = smoke_file(path)
    columns = [
        c
        for c in early
        if c not in ["target", "onset", "experiment", "detector_model", "second"]
    ]
    a = early.loc[early.second == 30, columns].to_numpy(dtype=float)
    b = later.loc[later.second == 30, columns].to_numpy(dtype=float)
    np.testing.assert_allclose(a, b)


def test_single_class_or_no_alerts_do_not_generate_fake_perfect_metrics():
    metric = binary_metrics([0, 0], [0.1, 0.2])
    assert metric["ap"] is None and metric["recall"] is None
    assert metric["precision"] is None and metric["roc_auc"] is None
