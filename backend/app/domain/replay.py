import json
import logging
import os
import re
import socket
import threading
import time
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Action,
    Equipment,
    HistoricalEvent,
    ImportOutbox,
    PredictionPoint,
    ProcessedSnapshot,
    SettingsRecord,
    utcnow,
)
from app.db.session import SessionLocal
from app.domain import actions as action_service
from app.domain import imports, smvu
from app.domain import replay_dispatcher as dispatcher
from app.domain import replay_scenarios as scenarios
from app.domain.equipment import RegistryError, lock_registry
from app.domain.predictions import get_prediction_source
from app.domain.replay_reader import JournalRow, journal_range, read_window
from app.schemas.replay import ScenarioItem

logger = logging.getLogger(__name__)

STATE_KEY = "replay"
EVENT_PREFIX = "replay:"
ACTOR = "Машина времени"
DRAFT_NOTE = "Черновик закрыт: журнал воспроизводится заново"
BATCH_PREFIXES = ("replay-", "scenario-")
WEEK_SENSORS = ("Состояние насоса", "Состояние вентилятора", "Датчик дыма", "Состояние фазы")
ACTIVE = ("preparing", "running", "stopping")
CONTROL = "control.json"
ACK = "control.ack.json"
TICK_SECONDS = 10.0
POLL_SECONDS = 2.0
STALE_SECONDS = 90
ACK_TIMEOUT_SECONDS = 1800
STAGE_TIMEOUT_SECONDS = 120
LAG_TIMEOUT_SECONDS = 600
DRAIN_TIMEOUT_SECONDS = 900
MAX_LEAD = timedelta(hours=24)
LOCK_ATTEMPTS = 20
MAX_WINDOW = timedelta(days=31)


class ReplayError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Stopped(Exception):
    pass


class Failed(Exception):
    pass


def _now() -> str:
    return utcnow().isoformat()


def _default() -> dict[str, Any]:
    return {
        "state": "idle",
        "mode": None,
        "run_id": None,
        "start": None,
        "end": None,
        "clock": None,
        "speed": None,
        "sent_events": 0,
        "batches": 0,
        "started_at": None,
        "finished_at": None,
        "detail": "",
        "simulate_dispatcher": False,
        "simulation": {"confirmed": 0, "dismissed": 0, "left": 0},
        "scenario": None,
        "item": None,
        "ml_history_end": None,
        "ml_clock": None,
        "live": True,
        "return_live": False,
        "owner": None,
        "heartbeat": None,
    }


def _load(record: SettingsRecord | None) -> dict[str, Any]:
    if record is None:
        return _default()
    try:
        stored = json.loads(record.value)
    except ValueError:
        stored = None
    return {**_default(), **(stored if isinstance(stored, dict) else {})}


def _lock(session: Session) -> tuple[SettingsRecord, dict[str, Any]]:
    session.execute(
        insert(SettingsRecord)
        .values(key=STATE_KEY, value=json.dumps(_default()), updated_at=utcnow())
        .on_conflict_do_nothing(index_elements=["key"])
    )
    record = session.scalars(
        select(SettingsRecord)
        .where(SettingsRecord.key == STATE_KEY)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    return record, _load(record)


def _save(record: SettingsRecord, state: dict[str, Any]) -> None:
    record.value = json.dumps(state, ensure_ascii=False)


def _alive(state: dict[str, Any]) -> bool:
    if state["state"] not in ACTIVE or not state.get("heartbeat"):
        return False
    try:
        beat = datetime.fromisoformat(state["heartbeat"])
    except ValueError:
        return False
    return (utcnow() - beat).total_seconds() <= STALE_SECONDS


def _owner(run_id: str) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{run_id}"


def _dataset(settings: Settings) -> Path | None:
    dataset = settings.dataset_dir
    return dataset if dataset is not None and dataset.is_dir() else None


def _journal_span(settings: Settings) -> tuple[datetime, datetime] | None:
    dataset = _dataset(settings)
    return journal_range(dataset) if dataset is not None else None


def _midnight(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def journal_time(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo(timezone)).replace(tzinfo=None)
    return value.replace(microsecond=0)


def event_id(run_id: str, original: str) -> str:
    return f"{EVENT_PREFIX}{run_id}:{original}"[:40]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_control(inbox: Path, replay_id: str, history_until: datetime | None) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    payload = {
        "replay_id": replay_id,
        "history_until": history_until.isoformat() if history_until else None,
        "requested_at": _now(),
    }
    temporary = inbox / f".{CONTROL}.tmp"
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, inbox / CONTROL)


def purge(session: Session) -> None:
    session.execute(
        delete(HistoricalEvent).where(
            HistoricalEvent.event_id.startswith(EVENT_PREFIX, autoescape=True)
        )
    )
    pending = session.scalars(select(ImportOutbox).where(ImportOutbox.delivered_at.is_(None)))
    for row in pending:
        payload = json.loads(row.payload)
        if payload.get("kind") == "stream" and str(payload.get("batch_id", "")).startswith(
            BATCH_PREFIXES
        ):
            row.delivered_at = utcnow()
    session.flush()


def close_drafts(session: Session, asset_ids: Collection[str] | None = None) -> None:
    statement = select(Action).where(Action.source == "vena_forecast", Action.status == "suggested")
    if asset_ids is not None:
        statement = statement.where(Action.asset_id.in_(asset_ids))
    for action in list(session.scalars(statement)):
        action_service.transition(session, action, "cancelled", ACTOR, DRAFT_NOTE)


def forget_snapshots(session: Session, since: datetime) -> None:
    moment = since.replace(tzinfo=UTC)
    session.execute(delete(PredictionPoint).where(PredictionPoint.prediction_time >= moment))
    session.execute(delete(ProcessedSnapshot).where(ProcessedSnapshot.prediction_time >= moment))


def week_channels(session: Session) -> set[str]:
    return set(
        session.scalars(
            select(Equipment.asset_id).where(
                Equipment.equipment_type.in_(WEEK_SENSORS), Equipment.status != "retired"
            )
        )
    )


def data_clock(settings: Settings, fallback: bool = True) -> datetime | None:
    status = get_prediction_source(settings).status()
    if status.available and status.prediction_time is not None:
        return dispatcher.wall_time(status.prediction_time)
    span = _journal_span(settings) if fallback else None
    return span[1] if span else None


def read_state(session: Session, settings: Settings) -> dict[str, Any]:
    state = _load(session.get(SettingsRecord, STATE_KEY))
    alive = _alive(state)
    if state["state"] in ACTIVE and not alive:
        state["state"] = "failed"
        state["detail"] = (
            "Воспроизведение прервано: процесс сервера остановился. "
            "Запустите заново или верните живой режим."
        )
    span = _journal_span(settings)
    return {
        **state,
        "active": alive,
        "journal_from": span[0] if span else None,
        "journal_to": span[1] if span else None,
    }


def time_machine(session: Session) -> dict[str, Any] | None:
    state = _load(session.get(SettingsRecord, STATE_KEY))
    if not _alive(state) and state["live"]:
        return None
    clock = state["clock"]
    return {**state, "clock": datetime.fromisoformat(clock) if clock else None}


def _require_stream(settings: Settings) -> Path:
    dataset = _dataset(settings)
    if dataset is None:
        raise ReplayError(503, "Каталог журнала не настроен на сервере (VENA_DATASET_DIR)")
    if settings.inbox_dir is None:
        raise ReplayError(503, "Приём потока событий не настроен на сервере (VENA_INBOX_DIR)")
    return dataset


def _claim(**fields: Any) -> dict[str, Any]:
    run_id = uuid4().hex[:8]
    with SessionLocal() as session:
        record, state = _lock(session)
        if _alive(state):
            raise ReplayError(
                409, "Машина времени уже работает. Остановите текущее воспроизведение."
            )
        purge(session)
        state = {
            **_default(),
            "live": state["live"],
            **fields,
            "run_id": run_id,
            "owner": _owner(run_id),
            "heartbeat": _now(),
            "started_at": _now(),
        }
        _save(record, state)
        session.commit()
    return state


def launch(runner: "Runner") -> None:
    threading.Thread(target=runner.run, name=f"replay-{runner.run_id}", daemon=True).start()


def start_week(
    settings: Settings, start: datetime, end: datetime, speed: float, simulate: bool
) -> dict[str, Any]:
    dataset = _require_stream(settings)
    start, end = journal_time(start, settings.timezone), journal_time(end, settings.timezone)
    if end <= start:
        raise ReplayError(422, "Конец периода должен быть позже начала")
    if end - start > MAX_WINDOW:
        raise ReplayError(422, "Период воспроизведения — не больше 31 дня")
    span = journal_range(dataset)
    if span is None:
        raise ReplayError(409, "В каталоге журнала нет файлов ext-journal-*.csv")
    if start < _midnight(span[0]) or end > _midnight(span[1]) + timedelta(days=1):
        raise ReplayError(
            409,
            f"Период вне журнала: доступны данные с {span[0]:%d.%m.%Y} по {span[1]:%d.%m.%Y}",
        )
    with SessionLocal() as session:
        if not week_channels(session):
            raise ReplayError(
                409, "В реестре нет каналов насосов, вентиляторов, дымовых датчиков и фаз"
            )
    state = _claim(
        state="preparing",
        mode="week",
        start=start.isoformat(),
        end=end.isoformat(),
        clock=start.isoformat(),
        speed=speed,
        simulate_dispatcher=simulate,
        live=False,
        detail=f"Подготовка: ML пересчитывает историю до {start:%d.%m.%Y %H:%M}",
    )
    launch(Runner(settings, state["run_id"]))
    return state


def start_scenario(settings: Settings, scenario_id: str) -> dict[str, Any]:
    _require_stream(settings)
    item = scenarios.find(settings, scenario_id)
    if item is None:
        raise ReplayError(404, "Сценарий не найден в каталоге")
    with SessionLocal() as session:
        if (
            session.scalar(select(Equipment.asset_id).where(Equipment.object_id == item.object))
            is None
        ):
            raise ReplayError(409, f"Каналы объекта {item.object} отсутствуют в реестре")
    state = _claim(
        state="preparing",
        mode="scenario",
        item=item.model_dump(mode="json"),
        scenario={"id": item.id, "kind": item.kind, "label": item.label, "object": item.object},
        detail=f"Учебный сценарий: {item.label}, объект {item.object}: чтение журнала",
    )
    launch(Runner(settings, state["run_id"]))
    return state


def stop(settings: Settings, return_live: bool) -> dict[str, Any]:
    follow_up = None
    with SessionLocal() as session:
        record, state = _lock(session)
        if _alive(state):
            return_live = return_live or state["return_live"]
            state.update(
                state="stopping",
                return_live=return_live,
                detail="Возврат в живой режим" if return_live else "Остановка воспроизведения",
            )
        elif return_live:
            if settings.inbox_dir is None:
                raise ReplayError(
                    503, "Приём потока событий не настроен на сервере (VENA_INBOX_DIR)"
                )
            follow_up = uuid4().hex[:8]
            state.update(
                state="stopping",
                run_id=follow_up,
                owner=_owner(follow_up),
                heartbeat=_now(),
                return_live=True,
                detail="Возврат в живой режим",
            )
        elif state["state"] in ACTIVE:
            state.update(state="finished", finished_at=_now(), detail="Воспроизведение остановлено")
        _save(record, state)
        session.commit()
    if follow_up is not None:
        launch(Runner(settings, follow_up))
    return state


class Runner:
    def __init__(
        self,
        settings: Settings,
        run_id: str,
        tick_seconds: float = TICK_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.run_id = run_id
        self.tick_seconds = tick_seconds
        self.sleep = sleep
        self.monotonic = monotonic

    @property
    def inbox(self) -> Path:
        if self.settings.inbox_dir is None:
            raise Failed("Приём потока событий не настроен на сервере (VENA_INBOX_DIR)")
        return self.settings.inbox_dir

    @property
    def dataset(self) -> Path:
        dataset = _dataset(self.settings)
        if dataset is None:
            raise Failed("Каталог журнала не настроен на сервере (VENA_DATASET_DIR)")
        return dataset

    def _check(self, state: dict[str, Any], allow_stopping: bool = False) -> None:
        if (
            state["run_id"] != self.run_id
            or state["state"] not in ACTIVE
            or (state["state"] == "stopping" and not allow_stopping)
        ):
            raise Stopped

    def _peek(self) -> dict[str, Any]:
        with SessionLocal() as session:
            return _load(session.get(SettingsRecord, STATE_KEY))

    def _beat(self, allow_stopping: bool = False, **fields: Any) -> dict[str, Any]:
        with SessionLocal() as session:
            record, state = _lock(session)
            self._check(state, allow_stopping)
            state.update(fields, heartbeat=_now())
            _save(record, state)
            session.commit()
            return state

    def _finish(self, name: str, detail: str, **fields: Any) -> None:
        with SessionLocal() as session:
            record, state = _lock(session)
            if state["run_id"] != self.run_id:
                return
            state.update(fields)
            state.update(
                state=name, detail=detail, finished_at=_now(), heartbeat=_now(), return_live=False
            )
            _save(record, state)
            session.commit()

    def _pause(self, seconds: float) -> None:
        deadline = self.monotonic() + seconds
        while (remaining := deadline - self.monotonic()) > 0:
            self.sleep(min(remaining, POLL_SECONDS))
            self._check(self._peek())

    def run(self) -> None:
        try:
            state = self._peek()
            self._check(state, allow_stopping=True)
            if state["state"] == "stopping":
                raise Stopped
            if state["mode"] == "week":
                self._week(state)
            else:
                self._scenario(state)
        except Stopped:
            state = self._peek()
            if state["run_id"] != self.run_id:
                return
            if state["return_live"]:
                self._return_live()
            else:
                self._finish("finished", "Воспроизведение остановлено администратором")
        except Failed as error:
            self._finish("failed", str(error))
        except Exception:
            logger.exception("replay %s failed", self.run_id)
            self._finish(
                "failed", "Внутренняя ошибка воспроизведения. Подробности в журнале сервера."
            )

    def _return_live(self) -> None:
        try:
            with SessionLocal() as session:
                purge(session)
                close_drafts(session)
                session.commit()
            replay_id = f"live-{self.run_id}"
            write_control(self.inbox, replay_id, None)
            ack = self._await_ack(
                replay_id, "Возврат в живой режим: ML пересчитывает полную историю", True
            )
            self._finish(
                "idle",
                "Живой режим восстановлен",
                live=True,
                clock=None,
                ml_history_end=ack.get("history_end"),
            )
        except Stopped:
            return
        except Failed as error:
            self._finish("failed", str(error))
        except Exception:
            logger.exception("return to live mode %s failed", self.run_id)
            self._finish("failed", "Не удалось вернуть живой режим. Подробности в журнале сервера.")

    def _await_ack(
        self, replay_id: str, label: str, allow_stopping: bool = False
    ) -> dict[str, Any]:
        began = self.monotonic()
        while True:
            ack = read_json(self.inbox / ACK)
            if isinstance(ack, dict) and ack.get("replay_id") == replay_id:
                if ack.get("error"):
                    raise Failed(f"ML не смог подготовить историю: {ack['error']}")
                return ack
            elapsed = self.monotonic() - began
            if elapsed > ACK_TIMEOUT_SECONDS:
                raise Failed(
                    "ML не подтвердил пересчёт истории за 30 минут. Проверьте сервис прогнозов."
                )
            self._beat(allow_stopping, detail=f"{label} · {int(elapsed)} с")
            self.sleep(POLL_SECONDS)

    def _publish(self) -> None:
        with SessionLocal() as session:
            try:
                imports.publish_pending(session, self.settings)
            except (RegistryError, OSError, ValueError):
                session.rollback()

    def _send(self, rows: list[JournalRow], batch_id: str, detail: str, **fields: Any) -> int:
        events = [
            {
                "event_id": event_id(self.run_id, row.event_id),
                "channel_id": row.channel_id,
                "ts": row.ts,
                "value": row.value[:120],
                "alarm": row.alarm,
            }
            for row in rows
        ]
        for _ in range(LOCK_ATTEMPTS):
            with SessionLocal() as session:
                record, state = _lock(session)
                self._check(state)
                added = 0
                if events:
                    try:
                        lock_registry(session)
                    except RegistryError:
                        session.rollback()
                        self.sleep(0.5)
                        continue
                    try:
                        latest, added = smvu.queue_events(
                            session, events, batch_id, self.settings.timezone, None
                        )
                    except RegistryError as error:
                        raise Failed(f"Пакет {batch_id} не принят: {error}") from None
                    smvu.accept_batch(
                        session,
                        batch_id=batch_id,
                        event_count=added,
                        last_event_at=latest,
                        detail=detail,
                    )
                state.update(fields, detail=detail, heartbeat=_now())
                state["sent_events"] += added
                state["batches"] += 1 if events else 0
                _save(record, state)
                session.commit()
            if events:
                self._publish()
            return added
        raise Failed("Реестр каналов занят обновлением: пакет событий не отправлен")

    def _simulate(self, since: datetime, clock: datetime) -> None:
        with SessionLocal() as session:
            record, state = _lock(session)
            self._check(state)
            counts = dispatcher.simulate(session, since, clock, self.settings.timezone)
            total = state["simulation"]
            state["simulation"] = {
                "confirmed": total["confirmed"] + counts["confirmed"],
                "dismissed": total["dismissed"] + counts["dismissed"],
                "left": counts["left"],
            }
            state["heartbeat"] = _now()
            _save(record, state)
            session.commit()

    def _await_ml(self, target: datetime, detail: str, timeout: float) -> bool:
        began = self.monotonic()
        while True:
            clock = data_clock(self.settings, fallback=False)
            if clock is None or clock >= target:
                return True
            if self.monotonic() - began >= timeout:
                return False
            self._beat(
                detail=f"{detail} · прогноз рассчитан на {clock:%d.%m %H:%M}",
                ml_clock=clock.isoformat(),
            )
            self.sleep(POLL_SECONDS)

    def _await_refresh(self, detail: str) -> None:
        began = self.monotonic()
        while self.monotonic() - began < STAGE_TIMEOUT_SECONDS:
            status = get_prediction_source(self.settings).status()
            if status.snapshot_id is None:
                return
            with SessionLocal() as session:
                if session.get(ProcessedSnapshot, status.snapshot_id) is not None:
                    return
            self._beat(detail=detail)
            self.sleep(POLL_SECONDS)

    def _ml_clock(self) -> str | None:
        clock = data_clock(self.settings, fallback=False)
        return clock.isoformat() if clock else None

    def _week(self, state: dict[str, Any]) -> None:
        start = datetime.fromisoformat(state["start"])
        end = datetime.fromisoformat(state["end"])
        dataset = self.dataset
        replay_id = f"replay-{self.run_id}"
        with SessionLocal() as session:
            close_drafts(session)
            session.commit()
        write_control(self.inbox, replay_id, start)
        ack = self._await_ack(
            replay_id, f"Подготовка: ML пересчитывает историю до {start:%d.%m.%Y %H:%M}"
        )
        history_end = datetime.fromisoformat(ack.get("history_end") or state["start"])
        with SessionLocal() as session:
            forget_snapshots(session, min(history_end.replace(tzinfo=None), start))
            session.commit()
        self._beat(
            state="running",
            ml_history_end=ack.get("history_end"),
            ml_clock=self._ml_clock(),
            detail=f"ML готов, история до {start:%d.%m.%Y %H:%M}",
        )
        with SessionLocal() as session:
            channels = week_channels(session)
        since = datetime.fromisoformat(state["started_at"])
        step = timedelta(seconds=float(state["speed"]) * self.tick_seconds)
        lead = max(step, MAX_LEAD)
        clock, number, latest, lockstep = start, 0, None, True
        while clock < end:
            upper = min(clock + step, end)
            if lockstep and latest is not None:
                lockstep = self._await_ml(
                    min(upper - lead, latest),
                    f"Ждём пересчёт прогноза перед {upper:%d.%m %H:%M}",
                    LAG_TIMEOUT_SECONDS,
                )
            began = self.monotonic()
            rows = read_window(dataset, clock, upper, channels)
            number += 1 if rows else 0
            latest = rows[-1].ts if rows else latest
            self._send(
                rows,
                f"replay-{self.run_id}-{number:04d}",
                f"Машина времени: {clock:%d.%m %H:%M} — {upper:%d.%m %H:%M}"
                + ("" if rows else ", событий нет"),
                clock=upper.isoformat(),
                ml_clock=self._ml_clock(),
            )
            clock = upper
            if state["simulate_dispatcher"]:
                self._simulate(since, clock)
            if clock < end:
                self._pause(self.tick_seconds - (self.monotonic() - began))
        if lockstep and latest is not None:
            waiting = "Все события отправлены, ждём последний пересчёт прогноза"
            if self._await_ml(latest, waiting, DRAIN_TIMEOUT_SECONDS):
                self._await_refresh(waiting)
            if state["simulate_dispatcher"]:
                self._simulate(since, end)
        sent = self._peek()["sent_events"]
        self._finish(
            "finished",
            f"Воспроизведение завершено: {sent} событий за {start:%d.%m.%Y} — {end:%d.%m.%Y}",
            ml_clock=self._ml_clock(),
        )

    def _scenario(self, state: dict[str, Any]) -> None:
        item = ScenarioItem.model_validate(state["item"])
        dataset = self.dataset
        with SessionLocal() as session:
            channels = set(
                session.scalars(
                    select(Equipment.asset_id).where(Equipment.object_id == item.object)
                )
            )
        if not channels:
            raise Failed(f"Каналы объекта {item.object} отсутствуют в реестре")
        with SessionLocal() as session:
            close_drafts(session, channels)
            session.commit()
            scored = channels & week_channels(session)
        rows = read_window(dataset, *scenarios.window(item), channels)
        if not rows:
            raise Failed(f"В журнале нет событий объекта {item.object} за период сценария")
        days = scenarios.shift_days(rows[0].ts, data_clock(self.settings))
        shift = timedelta(days=days)
        replayed = item.start + shift
        stages = scenarios.split_stages(rows, item.start, days)
        progress = {
            **state["scenario"],
            "stage": None,
            "stage_index": 0,
            "stages": len(stages),
            "shift_days": days,
            "replay_date": replayed.isoformat(),
        }
        self._beat(
            state="running",
            scenario=progress,
            start=(rows[0].ts + shift).isoformat(),
            end=(rows[-1].ts + shift).isoformat(),
            clock=(rows[0].ts + shift).isoformat(),
        )
        kind = re.sub(r"[^A-Za-z0-9_-]", "", item.kind)[:20] or "item"
        for index, (name, part) in enumerate(stages, start=1):
            detail = (
                f"Учебный сценарий: {item.label}, объект {item.object}, "
                f"повтор {replayed:%d.%m.%Y}, этап «{name}»"
            )
            self._send(
                part,
                f"scenario-{kind}-{self.run_id}-{index}",
                detail,
                clock=part[-1].ts.isoformat(),
                scenario={**progress, "stage": name, "stage_index": index},
            )
            relevant = [row.ts for row in part if row.channel_id in scored]
            if relevant:
                self._await_ml(relevant[-1], detail, STAGE_TIMEOUT_SECONDS)
        self._finish(
            "finished",
            f"Сценарий воспроизведён: {item.label}, объект {item.object}, "
            f"повтор {replayed:%d.%m.%Y}",
        )
