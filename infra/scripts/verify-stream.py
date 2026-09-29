import csv
import json
import tempfile
from pathlib import Path

import pandas as pd

import score_snapshot
from pipeline import config
from stream_scoring import StreamScorer

with tempfile.TemporaryDirectory(prefix="vena-stream-check-") as directory:
    root = Path(directory)
    config.CACHE_DIR = str(root / "cache")
    Path(config.CACHE_DIR).mkdir()
    config.CHANNELS_FILE = str(root / "channels.csv")
    config.JOURNAL_FILES = [str(root / "journal.csv")]
    with open(config.CHANNELS_FILE, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ид_канала_данных", "тип_инж_системы", "тип_датчика", "тег_инженерной_системы", "название_датчика", "ид_объект"])
        writer.writerow(["test-pump-001", "Водоотведение", "Состояние насоса", "0001.0002.0003.0004", "Тестовый насос ПК1", "42"])
    events = score_snapshot._synthetic_channel_events("test-pump-001", pd.Timestamp("2026-06-01"), "high", 42)
    with open(config.JOURNAL_FILES[0], "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ид_события", "ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"])
        for index, row in enumerate(events.itertuples()):
            writer.writerow([str(index), row.channel_id, row.ts.strftime("%Y-%m-%d"), row.ts.strftime("%H:%M:%S"), "t" if row.alarm_flag else "f", row.raw_value])
    scorer = StreamScorer(score_snapshot.channel_reference())
    first = scorer.score()
    assert first and {row["channel_id"] for row in first} == {"test-pump-001"}
    assert {str(row["object_id"]) for row in first} == {"42"}
    previous_time = scorer.now
    affected = scorer.ingest(pd.DataFrame([{"channel_id": "test-pump-001", "ts": previous_time + pd.Timedelta(hours=1), "alarm_flag": 1, "raw_value": "Неисправен"}]))
    second = scorer.score(affected)
    assert second and scorer.now > previous_time
    output = str(root / "snapshot.json")
    scorer.publish(output, {}, stream={"events": 1, "channels_rescored": 1, "received_at": "2026-06-01T00:00:00Z", "published_at": "2026-06-01T00:00:01Z", "latency_seconds": 1})
    snapshot = json.loads(Path(output).read_text())
    assert snapshot["data_source"] == "journal" and snapshot["stream"]["channels_rescored"] == 1
    assert {row["channel_id"] for row in snapshot["predictions"]} == {"test-pump-001"}
    print(f"PASS: isolated synthetic fixture, CSV dictionary/object 42, {len(first)} forecasts, stream rescore and snapshot publication; no production data changed")
