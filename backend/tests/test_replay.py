import json
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import (
    Action,
    AuditLog,
    Equipment,
    HistoricalEvent,
    ImportOutbox,
    PredictionPoint,
    ProcessedSnapshot,
    SettingsRecord,
    SmvuIngestState,
)
from app.db.session import SessionLocal
from app.domain import replay, replay_dispatcher, replay_reader, replay_scenarios
from app.domain.predictions import reset_prediction_source

HEADER = "ид_события,ид_канала_данных,дата,время,тревожное,значение_датчика\n"
MSK = ZoneInfo("Europe/Moscow")
CHANNELS = [
    ("101", "10", "Состояние насоса"),
    ("102", "10", "Состояние вентилятора"),
    ("103", "20", "Датчик дыма"),
    ("104", "20", "Состояние фазы"),
    ("105", "10", "КД Дверь"),
    ("106", "10", "Состояние насоса"),
    ("107", "30", "Состояние насоса"),
]


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def line(event_id: int | str, channel: str, ts: datetime, value: str, alarm: bool = False) -> str:
    return f"{event_id},{channel},{ts:%Y-%m-%d},{ts:%H:%M:%S},{'t' if alarm else 'f'},{value}\n"


def half_hour_journal(path: Path, start: datetime, hours: int, channels: list[str]) -> None:
    ids = count(1_000_000)
    rows = [
        line(next(ids), channel, start + timedelta(minutes=30 * step), "Норма")
        for step in range(hours * 2)
        for channel in channels
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "".join(rows), encoding="utf-8")


def seed_equipment() -> None:
    with SessionLocal.begin() as session:
        for asset_id, object_id, sensor in CHANNELS:
            session.add(
                Equipment(
                    asset_id=asset_id,
                    external_id=asset_id,
                    source="test",
                    name=f"{sensor} {asset_id}",
                    object_id=object_id,
                    equipment_type=sensor,
                )
            )


@pytest.fixture()
def stand(client: TestClient, monkeypatch, tmp_path: Path):
    settings = get_settings()
    dataset = tmp_path / "dataset"
    inbox = tmp_path / "inbox"
    ml_dir = tmp_path / "ml"
    half_hour_journal(
        dataset / "ext-journal-2026.csv",
        datetime(2026, 6, 1, 0, 0),
        72,
        [channel for channel, _, _ in CHANNELS],
    )
    monkeypatch.setattr(settings, "dataset_dir", dataset)
    monkeypatch.setattr(settings, "inbox_dir", inbox)
    monkeypatch.setattr(settings, "ml_dir", ml_dir)
    reset_prediction_source()
    launched: list[replay.Runner] = []
    monkeypatch.setattr(replay, "launch", launched.append)
    seed_equipment()
    yield {
        "client": client,
        "settings": settings,
        "dataset": dataset,
        "inbox": inbox,
        "ml": ml_dir,
        "runs": launched,
    }
    reset_prediction_source()


def drive(runner: replay.Runner, inbox: Path, replay_id: str | None = None) -> FakeTime:
    clock = FakeTime()
    runner.sleep = clock.sleep
    runner.monotonic = clock.monotonic
    if replay_id is not None:
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "control.ack.json").write_text(
            json.dumps({"replay_id": replay_id, "history_end": "2026-06-01T23:30:00"}),
            encoding="utf-8",
        )
    runner.run()
    return clock


def state() -> dict:
    with SessionLocal() as session:
        record = session.get(SettingsRecord, "replay")
        assert record is not None
        return json.loads(record.value)


def test_reader_binary_search_spans_files(tmp_path: Path) -> None:
    ids = count(1_000_000)
    first = [
        line(next(ids), "7", datetime(2025, 12, 29) + timedelta(minutes=minute), "0.01")
        for minute in range(3 * 1440)
    ]
    second = [
        line(next(ids), "7", datetime(2026, 1, 1) + timedelta(minutes=minute), "0.02")
        for minute in range(3 * 1440)
    ]
    second.insert(1500, line(next(ids), "7", datetime(2026, 1, 9, 12), "Неисправен"))
    (tmp_path / "ext-journal-2025.csv").write_text(HEADER + "".join(first), encoding="utf-8")
    (tmp_path / "ext-journal-2026.csv").write_text(HEADER + "".join(second), encoding="utf-8")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    duplicate = second[30].split(",")[0]
    (uploads / "ext-journal-run1.csv").write_text(
        '"ид_события","ид_канала_данных","дата","время","тревожное","значение_датчика"\n'
        f'{duplicate},7,"2026-01-01","00:30:00",false,"0.02"\n'
        '900001,9,"2026-01-01","00:45:00",true,"Неисправен"\n',
        encoding="utf-8",
    )
    path = tmp_path / "ext-journal-2026.csv"
    assert path.stat().st_size > 2 * replay_reader.BLOCK

    target = datetime(2026, 1, 2, 12)
    low, high = replay_reader.locate(path, target)
    assert high - low <= replay_reader.BLOCK
    with path.open("rb") as handle:
        assert replay_reader._probe(handle, low) < target
        assert replay_reader._probe(handle, high) >= target

    first_day, last_seen = replay_reader.journal_range(tmp_path)
    assert first_day.date() == datetime(2025, 12, 29).date()
    assert last_seen == replay_reader.file_span(path)[1] > datetime(2026, 1, 3, 22)
    rows = replay_reader.read_window(
        tmp_path, datetime(2025, 12, 31, 22), datetime(2026, 1, 1, 2), {"7", "9"}
    )
    stamps = [row.ts for row in rows if row.channel_id == "7"]
    assert len(stamps) == 240
    assert stamps[0] == datetime(2025, 12, 31, 22) and stamps[-1] == datetime(2026, 1, 1, 1, 59)
    assert stamps == sorted(stamps)
    assert len({row.event_id for row in rows}) == len(rows)
    upload = [row for row in rows if row.channel_id == "9"]
    assert [(row.value, row.alarm) for row in upload] == [("Неисправен", True)]

    late = replay_reader.read_window(
        tmp_path, datetime(2026, 1, 2, 23), datetime(2026, 1, 3, 1), {"7"}
    )
    assert len(late) == 120 and all(row.ts < datetime(2026, 1, 3, 1) for row in late)
    assert replay_reader.read_window(tmp_path, datetime(2027, 1, 1), datetime(2027, 1, 2)) == []


def test_week_runner_slices_ticks_and_spools_events(stand) -> None:
    with SessionLocal.begin() as session:
        session.add(
            HistoricalEvent(
                event_id="real-1",
                channel_id="101",
                ts=datetime(2026, 5, 1, tzinfo=MSK),
                value="Норма",
                alarm=False,
            )
        )
        session.add(
            HistoricalEvent(
                event_id="replay:old:1",
                channel_id="101",
                ts=datetime(2026, 5, 1, tzinfo=MSK),
                value="Норма",
                alarm=False,
            )
        )
        session.add(
            ImportOutbox(
                id="stale",
                payload=json.dumps({"kind": "stream", "batch_id": "replay-old-0001", "events": []}),
            )
        )
        earlier = datetime.now(tz=UTC) - timedelta(hours=1)
        make_action(session, "A-9001", "101", "pump_24h", datetime(2026, 6, 30), earlier)
        planned = make_action(session, "A-9002", "102", "fan_24h", datetime(2026, 6, 30), earlier)
        planned.status = "planned"
        for snapshot_id, moment in (
            ("live", datetime(2026, 6, 30)),
            ("past", datetime(2026, 5, 1)),
        ):
            session.add(
                ProcessedSnapshot(
                    snapshot_id=snapshot_id, prediction_time=moment.replace(tzinfo=UTC)
                )
            )
            session.add(
                PredictionPoint(
                    snapshot_id=snapshot_id,
                    asset_id="101",
                    model_id="pump_24h",
                    score=0.5,
                    prediction_time=moment.replace(tzinfo=UTC),
                )
            )

    client = stand["client"]
    response = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-06-02T00:00:00", "end": "2026-06-03T00:00:00", "speed": 2160},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "preparing" and body["active"] is True and body["live"] is False
    runner = stand["runs"][-1]
    assert not (stand["inbox"] / "control.json").exists()

    drive(runner, stand["inbox"], f"replay-{runner.run_id}")

    control = json.loads((stand["inbox"] / "control.json").read_text(encoding="utf-8"))
    assert control["replay_id"] == f"replay-{runner.run_id}"
    assert control["history_until"] == "2026-06-02T00:00:00"
    result = state()
    assert result["state"] == "finished"
    assert result["clock"] == "2026-06-03T00:00:00"
    assert result["batches"] == 4
    assert result["sent_events"] == 6 * 48
    assert result["ml_history_end"] == "2026-06-01T23:30:00"
    with SessionLocal() as session:
        ids = list(session.scalars(select(HistoricalEvent.event_id)))
        assert "real-1" in ids and "replay:old:1" not in ids
        draft = session.get(Action, "A-9001")
        assert draft is not None and draft.status == "cancelled"
        assert draft.history[-1].actor == "Машина времени"
        assert draft.history[-1].note == replay.DRAFT_NOTE
        kept = session.get(Action, "A-9002")
        assert kept is not None and kept.status == "planned"
        assert set(session.scalars(select(ProcessedSnapshot.snapshot_id))) == {"past"}
        assert set(session.scalars(select(PredictionPoint.snapshot_id))) == {"past"}
        replayed = [value for value in ids if value.startswith(f"replay:{runner.run_id}:")]
        assert len(replayed) == 6 * 48
        channels = set(
            session.scalars(
                select(HistoricalEvent.channel_id).where(
                    HistoricalEvent.event_id.startswith("replay:")
                )
            )
        )
        assert channels == {"101", "102", "103", "104", "106", "107"}
        bounds = session.execute(
            select(func.min(HistoricalEvent.ts), func.max(HistoricalEvent.ts)).where(
                HistoricalEvent.event_id.startswith("replay:")
            )
        ).one()
        assert bounds[0] == datetime(2026, 6, 2, tzinfo=MSK)
        assert bounds[1] == datetime(2026, 6, 2, 23, 30, tzinfo=MSK)
        stale = session.get(ImportOutbox, "stale")
        assert stale is not None and stale.delivered_at is not None
        smvu = session.get(SmvuIngestState, "default")
        assert smvu is not None and smvu.last_batch_id == f"replay-{runner.run_id}-0004"
        assert smvu.detail.startswith("Машина времени: 02.06 18:00")
    spooled = sorted(
        path for path in stand["inbox"].glob("stream-*.jsonl") if path.name != "stream-stale.jsonl"
    )
    assert len(spooled) == 4
    first = [json.loads(row) for row in spooled[0].read_text(encoding="utf-8").splitlines()]
    assert all(row["event_id"].startswith(f"replay:{runner.run_id}:") for row in first)

    again = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-06-02T00:00:00", "end": "2026-06-02T06:00:00", "speed": 2160},
    )
    assert again.status_code == 202
    second = stand["runs"][-1]
    drive(second, stand["inbox"], f"replay-{second.run_id}")
    with SessionLocal() as session:
        prefixes = {
            value.split(":")[1]
            for value in session.scalars(select(HistoricalEvent.event_id))
            if value.startswith("replay:")
        }
        assert prefixes == {second.run_id}


def write_snapshot(ml_dir: Path, prediction_time: str) -> None:
    path = ml_dir / "results" / "predictions" / "snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "snapshot_id": "s1",
                "prediction_time": prediction_time,
                "data_source": "journal",
                "models": {},
                "predictions": [],
            }
        ),
        encoding="utf-8",
    )


def test_week_runner_keeps_pace_with_scoring(stand, monkeypatch) -> None:
    client = stand["client"]
    week = {"start": "2026-06-02T00:00:00", "end": "2026-06-04T00:00:00", "speed": 2160}
    monkeypatch.setattr(replay, "LAG_TIMEOUT_SECONDS", 6)
    write_snapshot(stand["ml"], "2026-06-02T00:00:00")
    assert client.post("/api/v1/replay/week", json=week).status_code == 202
    runner = stand["runs"][-1]
    stalled = drive(runner, stand["inbox"], f"replay-{runner.run_id}")
    result = state()
    assert result["state"] == "finished"
    assert result["sent_events"] == 6 * 96 and result["batches"] == 8
    assert result["ml_clock"] == "2026-06-02T00:00:00"
    assert stalled.now == 7 * runner.tick_seconds + 6

    write_snapshot(stand["ml"], "2026-06-05T00:00:00")
    reset_prediction_source()
    with SessionLocal.begin() as session:
        session.add(ProcessedSnapshot(snapshot_id="s1", prediction_count=0))
    assert client.post("/api/v1/replay/week", json=week).status_code == 202
    runner = stand["runs"][-1]
    steady = drive(runner, stand["inbox"], f"replay-{runner.run_id}")
    assert state()["state"] == "finished"
    assert steady.now == 7 * runner.tick_seconds


def make_action(
    session, action_id: str, asset_id: str, model_id: str, moment: datetime, created: datetime
) -> Action:
    action = Action(
        id=action_id,
        asset_id=asset_id,
        source="vena_forecast",
        source_detail=model_id,
        kind="inspect",
        reason="test",
        priority="medium",
        window_start=created,
        recommended_at=created,
        status="suggested",
        assignee="Дежурный инженер",
        created_by="vena-ingest",
        created_at=created,
        updated_at=created,
        source_model_id=model_id,
        source_prediction_time=moment.replace(tzinfo=UTC),
        source_horizon_hours=24,
    )
    session.add(action)
    return action


def test_simulated_dispatcher_confirms_dismisses_and_leaves(client: TestClient) -> None:
    seed_equipment()
    since = datetime.now(tz=UTC) - timedelta(minutes=5)
    moment = datetime(2026, 6, 2, 6, 0)
    taken: set[str] = set()

    def fresh(left: bool = False) -> str:
        value = next(
            f"A-{number}"
            for number in count(5000)
            if f"A-{number}" not in taken
            and (replay_dispatcher.share(f"A-{number}") < replay_dispatcher.LEAVE_SHARE) == left
        )
        taken.add(value)
        return value

    confirmed_id, foreign_id, dismissed_id = fresh(), fresh(), fresh()
    left_id, young_id, old_id = fresh(left=True), fresh(), fresh()
    with SessionLocal.begin() as session:
        make_action(session, confirmed_id, "101", "pump_24h", moment, since + timedelta(minutes=1))
        make_action(session, foreign_id, "103", "smoke_24h", moment, since + timedelta(minutes=1))
        make_action(session, dismissed_id, "104", "phase_24h", moment, since + timedelta(minutes=1))
        make_action(session, left_id, "102", "fan_24h", moment, since + timedelta(minutes=1))
        make_action(
            session,
            young_id,
            "107",
            "pump_24h",
            moment + timedelta(hours=12),
            since + timedelta(minutes=1),
        )
        make_action(session, old_id, "107", "pump_24h", moment, since - timedelta(hours=1))
        events = [
            ("e1", "106", moment + timedelta(hours=5), "Неисправен"),
            ("e2", "105", moment + timedelta(hours=2), "Неисправен"),
            ("e3", "101", moment - timedelta(hours=1), "Неисправен"),
            ("e4", "104", moment + timedelta(hours=30), "Обесточен"),
            ("e5", "107", moment + timedelta(hours=3), "Неисправен"),
        ]
        for event_id, channel, ts, value in events:
            session.add(
                HistoricalEvent(
                    event_id=event_id,
                    channel_id=channel,
                    ts=ts.replace(tzinfo=MSK),
                    value=value,
                    alarm=False,
                )
            )

    with SessionLocal() as session:
        counts = replay_dispatcher.simulate(
            session, since, moment + timedelta(hours=24), "Europe/Moscow"
        )
        session.commit()
    assert counts == {"confirmed": 1, "dismissed": 2, "left": 1}

    with SessionLocal() as session:
        confirmed = session.get(Action, confirmed_id)
        assert confirmed is not None and confirmed.status == "completed"
        assert confirmed.result_outcome in {"confirmed_issue", "maintenance_performed"}
        assert confirmed.result_note == "Симуляция: событие в журнале через 5 ч после прогноза"
        assert confirmed.assignee in replay_dispatcher.CREWS
        assert [event.event_type for event in confirmed.history] == [
            "approved",
            "assigned",
            "started",
            "completed",
            "result_recorded",
        ]
        assert {event.actor for event in confirmed.history} == {"Симуляция диспетчера"}
        for action_id in (foreign_id, dismissed_id):
            dismissed = session.get(Action, action_id)
            assert dismissed is not None and dismissed.status == "dismissed"
            assert dismissed.result_note.endswith(
                "Симуляция: в горизонте прогноза событие не наступило"
            )
            assert replay_dispatcher.dismiss_reason(action_id) in {
                "verified_normal",
                "monitoring",
                "false_alarm",
            }
        for action_id in (left_id, young_id, old_id):
            untouched = session.get(Action, action_id)
            assert untouched is not None and untouched.status == "suggested"

    assert replay_dispatcher.target_state("smoke_alarm_24h") == "Обнаружен дым"
    assert replay_dispatcher.target_state("smoke_24h") == "Неисправен"
    assert replay_dispatcher.target_state("flood_24h") == "Затоплен"
    assert replay_dispatcher.target_state("phase_24h") == "Обесточен"
    assert replay_dispatcher.target_state("fan_72h") == "Неисправен"
    assert replay_dispatcher.target_state("alarm_30m") is None


def test_scenario_shift_and_stages() -> None:
    first = datetime(2026, 6, 2, 8)
    assert replay_scenarios.shift_days(first, datetime(2026, 6, 5, 12)) == 4
    assert replay_scenarios.shift_days(first, datetime(2026, 6, 3, 8)) == 2
    assert replay_scenarios.shift_days(first, datetime(2026, 6, 1)) == 0
    assert replay_scenarios.shift_days(first, None) == 0
    rows = [
        replay_reader.JournalRow(str(hour), "1", datetime(2026, 6, 2, hour), False, "Норма")
        for hour in range(8, 23)
    ]
    stages = replay_scenarios.split_stages(rows, datetime(2026, 6, 2, 20), 3)
    assert [name for name, _ in stages] == ["предвестники", "развитие", "инцидент"]
    assert [len(part) for _, part in stages] == [6, 6, 3]
    assert stages[0][1][0].ts == datetime(2026, 6, 5, 8)
    assert stages[2][1][0].ts == datetime(2026, 6, 5, 20)
    late = replay_scenarios.split_stages(rows[-3:], datetime(2026, 6, 2, 20), 0)
    assert [name for name, _ in late] == ["инцидент"]


def write_catalog(ml_dir: Path) -> None:
    path = ml_dir / "results" / "scenarios" / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-10-16T17:00:00",
                "note": "тест",
                "summary": {"flood": {"incidents": 3, "share_top3": 0.41, "hours_before": 6}},
                "items": [
                    {
                        "id": "flood-10-20260602",
                        "kind": "flood",
                        "label": "Подтопление",
                        "object": 10,
                        "start": "2026-06-02T20:00:00",
                        "end": "2026-06-02T20:30:00",
                        "channels": 2,
                        "rule": "два насоса",
                        "before_hours": 12,
                        "after_hours": 2,
                        "lead": [{"hours_before": 6, "place": 3, "objects_ranked": 18}],
                    },
                    {"id": "broken", "start": "не дата"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_scenario_replays_object_in_three_stages(stand, monkeypatch) -> None:
    client = stand["client"]
    assert client.get("/api/v1/replay/scenarios").json()["items"] == []
    write_catalog(stand["ml"])
    catalog = client.get("/api/v1/replay/scenarios").json()
    assert [item["id"] for item in catalog["items"]] == ["flood-10-20260602"]
    assert catalog["items"][0]["object"] == "10"
    assert catalog["summary"]["flood"]["share_top3"] == 0.41
    write_snapshot(stand["ml"], "2026-06-05T12:00:00")
    monkeypatch.setattr(replay, "STAGE_TIMEOUT_SECONDS", 4)
    with SessionLocal.begin() as session:
        earlier = datetime.now(tz=UTC) - timedelta(hours=1)
        make_action(session, "A-9101", "106", "pump_24h", datetime(2026, 6, 5), earlier)
        make_action(session, "A-9102", "103", "smoke_24h", datetime(2026, 6, 5), earlier)

    assert client.post("/api/v1/replay/scenario", json={"id": "missing"}).status_code == 404
    response = client.post("/api/v1/replay/scenario", json={"id": "flood-10-20260602"})
    assert response.status_code == 202, response.text
    runner = stand["runs"][-1]
    drive(runner, stand["inbox"])
    assert not (stand["inbox"] / "control.json").exists()

    result = client.get("/api/v1/replay").json()
    assert result["state"] == "finished", result["detail"]
    assert result["mode"] == "scenario"
    assert result["scenario"]["shift_days"] == 4
    assert result["scenario"]["stage"] == "инцидент"
    assert result["scenario"]["stage_index"] == result["scenario"]["stages"] == 3
    assert result["scenario"]["replay_date"].startswith("2026-06-06T20:00:00")
    assert result["sent_events"] == 29 * 4
    assert result["batches"] == 3
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(HistoricalEvent).where(HistoricalEvent.event_id.startswith("replay:"))
            )
        )
        assert {row.channel_id for row in rows} == {"101", "102", "105", "106"}
        assert min(row.ts for row in rows) == datetime(2026, 6, 6, 8, tzinfo=MSK)
        assert max(row.ts for row in rows) == datetime(2026, 6, 6, 22, tzinfo=MSK)
        smvu = session.get(SmvuIngestState, "default")
        assert smvu is not None
        assert smvu.last_batch_id == f"scenario-flood-{runner.run_id}-3"
        assert smvu.detail == (
            "Учебный сценарий: Подтопление, объект 10, повтор 06.06.2026, этап «инцидент»"
        )
        assert session.get(Action, "A-9101").status == "cancelled"
        assert session.get(Action, "A-9102").status == "suggested"


def test_return_live_resets_ml_and_purges_replay_rows(stand) -> None:
    client = stand["client"]
    with SessionLocal.begin() as session:
        session.add(
            HistoricalEvent(
                event_id="replay:abc:1",
                channel_id="101",
                ts=datetime(2026, 6, 2, tzinfo=MSK),
                value="Норма",
                alarm=False,
            )
        )
    response = client.post("/api/v1/replay/stop", json={"return_live": True})
    assert response.status_code == 200
    assert response.json()["state"] == "stopping"
    runner = stand["runs"][-1]
    drive(runner, stand["inbox"], f"live-{runner.run_id}")
    control = json.loads((stand["inbox"] / "control.json").read_text(encoding="utf-8"))
    assert control["replay_id"] == f"live-{runner.run_id}"
    assert control["history_until"] is None
    result = client.get("/api/v1/replay").json()
    assert result["state"] == "idle" and result["live"] is True and result["active"] is False
    with SessionLocal() as session:
        assert session.get(HistoricalEvent, "replay:abc:1") is None


def test_week_fails_when_ml_does_not_confirm_reset(stand, monkeypatch) -> None:
    client = stand["client"]
    monkeypatch.setattr(replay, "ACK_TIMEOUT_SECONDS", 10)
    week = {"start": "2026-06-02T00:00:00", "end": "2026-06-03T00:00:00"}
    assert client.post("/api/v1/replay/week", json=week).status_code == 202
    waited = drive(stand["runs"][-1], stand["inbox"])
    result = client.get("/api/v1/replay").json()
    assert result["state"] == "failed" and result["active"] is False and result["live"] is False
    assert result["detail"].startswith("ML не подтвердил пересчёт истории")
    assert result["sent_events"] == 0
    assert 10 < waited.now <= 14


def test_stop_and_conflicts(stand) -> None:
    client = stand["client"]
    week = {"start": "2026-06-02T00:00:00", "end": "2026-06-03T00:00:00"}
    assert client.post("/api/v1/replay/week", json=week).status_code == 202
    busy = client.post("/api/v1/replay/week", json=week)
    assert busy.status_code == 409
    notices = {notice["id"]: notice for notice in client.get("/api/v1/system/notices").json()}
    assert "данные на 02.06.2026 00:00" in notices["time-machine"]["description"]
    assert "уже работает" in busy.json()["detail"]
    stopping = client.post("/api/v1/replay/stop", json={"return_live": False}).json()
    assert stopping["state"] == "stopping"
    drive(stand["runs"][0], stand["inbox"])
    result = client.get("/api/v1/replay").json()
    assert result["state"] == "finished"
    assert result["detail"] == "Воспроизведение остановлено администратором"

    assert client.post("/api/v1/replay/week", json=week).status_code == 202
    with SessionLocal.begin() as session:
        record = session.get(SettingsRecord, "replay")
        assert record is not None
        stored = json.loads(record.value)
        stored["heartbeat"] = (datetime.now(tz=UTC) - timedelta(minutes=10)).isoformat()
        record.value = json.dumps(stored)
    stale = client.get("/api/v1/replay").json()
    assert stale["state"] == "failed" and stale["active"] is False
    assert client.post("/api/v1/replay/week", json=week).status_code == 202
    with SessionLocal() as session:
        actions = list(
            session.scalars(select(AuditLog.action).where(AuditLog.resource_type == "replay"))
        )
    assert actions.count("replay.start") == 3 and "replay.stop" in actions


def test_week_validation(stand, monkeypatch) -> None:
    client = stand["client"]
    reversed_window = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-06-03T00:00:00", "end": "2026-06-02T00:00:00"},
    )
    assert reversed_window.status_code == 422
    assert reversed_window.json()["detail"] == "Конец периода должен быть позже начала"
    too_long = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-05-01T00:00:00", "end": "2026-06-03T00:00:00"},
    )
    assert too_long.status_code == 422
    outside = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-06-20T00:00:00", "end": "2026-06-27T00:00:00"},
    )
    assert outside.status_code == 409
    assert outside.json()["detail"].startswith("Период вне журнала: доступны данные с 01.06.2026")
    state_now = client.get("/api/v1/replay").json()
    assert state_now["journal_from"].startswith("2026-06-01T00:00:00")
    assert state_now["state"] == "idle" and state_now["live"] is True

    with SessionLocal.begin() as session:
        for equipment in session.scalars(select(Equipment)):
            equipment.equipment_type = "КД Дверь"
    no_channels = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-06-02T00:00:00", "end": "2026-06-03T00:00:00"},
    )
    assert no_channels.status_code == 409

    monkeypatch.setattr(get_settings(), "dataset_dir", None)
    missing = client.post(
        "/api/v1/replay/week",
        json={"start": "2026-06-02T00:00:00", "end": "2026-06-03T00:00:00"},
    )
    assert missing.status_code == 503


def test_replay_mutations_are_admin_only(client: TestClient, auth_users) -> None:
    week = {"start": "2026-06-02T00:00:00", "end": "2026-06-03T00:00:00"}
    viewer = client.get("/api/v1/replay", headers=auth_users["viewer"])
    assert viewer.status_code == 200
    assert viewer.json()["state"] == "idle"
    assert client.get("/api/v1/replay/scenarios", headers=auth_users["viewer"]).status_code == 200
    for role in ("viewer", "dispatcher"):
        headers = auth_users[role]
        assert client.post("/api/v1/replay/week", json=week, headers=headers).status_code == 403
        assert (
            client.post("/api/v1/replay/scenario", json={"id": "x"}, headers=headers).status_code
            == 403
        )
        assert client.post("/api/v1/replay/stop", json={}, headers=headers).status_code == 403
    assert client.get("/api/v1/replay").status_code == 401
    missing = client.post("/api/v1/replay/week", json=week, headers=auth_users["admin"])
    assert missing.status_code == 503
