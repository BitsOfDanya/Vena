import json

import pandas as pd


def test_control_requests_reset_only_for_a_new_replay():
    import stream_scoring

    control = {"replay_id": "r1", "history_until": "2026-06-01T00:00:00", "requested_at": "2026-10-16T10:00:00+00:00"}
    assert stream_scoring.control_reset(control, None) == ("r1", pd.Timestamp("2026-06-01T00:00:00"))
    assert stream_scoring.control_reset(control, "r0") == ("r1", pd.Timestamp("2026-06-01T00:00:00"))
    assert stream_scoring.control_reset(control, "r1") is None


def test_live_control_clears_the_history_limit():
    import stream_scoring

    assert stream_scoring.control_reset({"replay_id": "live-1", "history_until": None}, "r1") == ("live-1", None)


def test_aware_history_limit_keeps_journal_wall_time():
    import stream_scoring

    _, until = stream_scoring.control_reset({"replay_id": "r2", "history_until": "2026-06-01T00:00:00+03:00"}, "r1")
    assert until == pd.Timestamp("2026-06-01T00:00:00")
    assert until.tzinfo is None


def test_malformed_control_is_ignored():
    import stream_scoring

    assert stream_scoring.control_reset(None, "r1") is None
    assert stream_scoring.control_reset([], "r1") is None
    assert stream_scoring.control_reset({"history_until": "2026-06-01"}, "r1") is None
    assert stream_scoring.control_reset({"replay_id": "", "history_until": None}, "r1") is None
    assert stream_scoring.control_reset({"replay_id": "r2", "history_until": "не дата"}, "r1") is None


def test_archive_moves_processed_and_pending_events(tmp_path):
    import stream_scoring

    inbox = tmp_path
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "a.jsonl").write_text("{}\n", encoding="utf-8")
    (processed / ".replay_id").write_text(json.dumps({"replay_id": "r1"}), encoding="utf-8")
    (inbox / "b.jsonl").write_text("{}\n", encoding="utf-8")
    (inbox / "control.json").write_text("{}", encoding="utf-8")

    stream_scoring.archive_events(str(inbox), str(processed), "r1")

    batch, files = stream_scoring.read_inbox(str(processed))
    assert files == [] and batch.empty
    assert stream_scoring.read_inbox(str(inbox))[1] == []
    assert sorted(path.name for path in (processed / "archive-r1").iterdir()) == ["a.jsonl", "b.jsonl"]
    assert (inbox / "control.json").exists()
    assert (processed / ".replay_id").exists()
