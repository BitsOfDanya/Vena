"""Regression check for journal rows sharing a channel and timestamp."""

import hashlib
from pathlib import Path

from pipeline import config, extract


def test_extract_orders_tied_events_by_event_id(tmp_path, monkeypatch):
    """Repeated extraction keeps the same state sequence and cache bytes."""
    journal = tmp_path / "journal.csv"
    journal.write_text(
        "ид_события,ид_канала_данных,дата,время,тревожное,значение_датчика\n"
        "3,channel-1,2024-01-01,12:00:00,f,Выключен\n"
        "1,channel-1,2024-01-01,12:00:00,f,Включен\n"
        "2,channel-1,2024-01-01,12:00:00,t,Неисправен\n",
        encoding="utf-8",
    )
    channels = tmp_path / "channels.csv"
    channels.write_text(
        "ид_канала_данных,тип_инж_системы,тип_датчика,тег_инженерной_системы,название_датчика\n"
        "channel-1,Система,Состояние насоса,Тег,Насос\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "JOURNAL_FILES", [str(journal)])
    monkeypatch.setattr(config, "CHANNELS_FILE", str(channels))
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))

    first = extract.extract_events("Состояние насоса", force=True)
    cache = extract.cache_path("Состояние насоса")
    first_digest = hashlib.sha256(Path(cache).read_bytes()).hexdigest()
    second = extract.extract_events("Состояние насоса", force=True)
    second_digest = hashlib.sha256(Path(cache).read_bytes()).hexdigest()

    assert first["raw_value"].astype(str).tolist() == [
        "Включен", "Неисправен", "Выключен",
    ]
    assert first.equals(second)
    assert first_digest == second_digest
