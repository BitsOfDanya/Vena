from collections.abc import Callable

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import SessionLocal
from app.domain import equipment, helpdesk, imports
from app.domain.digest import send_digest
from app.domain.email import build_email_provider
from app.domain.ingest import refresh_predictions
from app.domain.mail_queue import deliver_pending
from app.domain.predictions import get_prediction_source
from app.domain.settings_store import read_settings
from app.domain.watchdog import escalate, notify_overdue_actions, watch_data_sources
from app.schemas.notifications import DigestSettings

_scheduler: BackgroundScheduler | None = None


def _run_digest(settings: Settings) -> None:
    session = SessionLocal()
    try:
        send_digest(session, settings, build_email_provider(settings))
        session.commit()
    finally:
        session.close()


def _run_refresh(settings: Settings) -> None:
    session = SessionLocal()
    try:
        refresh_predictions(
            session, settings, get_prediction_source(settings), build_email_provider(settings)
        )
        session.commit()
    finally:
        session.close()


def _run_equipment(settings: Settings) -> None:
    with SessionLocal() as session:
        try:
            equipment.synchronize(session, settings)
        except equipment.RegistryError:
            session.rollback()


def _run_helpdesk(settings: Settings) -> None:
    with SessionLocal() as session:
        helpdesk.synchronize(session, settings)
        session.commit()


def _run_publications(settings: Settings) -> None:
    with SessionLocal() as session:
        try:
            imports.publish_pending(session, settings)
        except equipment.RegistryError:
            session.rollback()


def _run_email(settings: Settings) -> None:
    with SessionLocal() as session:
        deliver_pending(session, build_email_provider(settings))


def _run_check(check: Callable[[Session, Settings], object], settings: Settings) -> None:
    with SessionLocal() as session:
        check(session, settings)
        session.commit()


def digest_trigger(settings: Settings, digest: DigestSettings) -> CronTrigger:
    return CronTrigger(
        hour=digest.hour, minute=digest.minute, timezone=digest.timezone or settings.timezone
    )


def reschedule_digest(settings: Settings, digest: DigestSettings) -> bool:
    if _scheduler is None:
        return False
    try:
        _scheduler.reschedule_job("morning_brief", trigger=digest_trigger(settings, digest))
    except JobLookupError:
        return False
    return True


def build_scheduler(settings: Settings) -> BackgroundScheduler | None:
    global _scheduler
    session = SessionLocal()
    try:
        digest = read_settings(session, settings).digest
    finally:
        session.close()
    scheduler = BackgroundScheduler(timezone=digest.timezone or settings.timezone)
    scheduler.add_job(
        _run_refresh,
        IntervalTrigger(seconds=settings.prediction_refresh_seconds),
        args=[settings],
        id="prediction_refresh",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_digest,
        digest_trigger(settings, digest),
        args=[settings],
        id="morning_brief",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_publications,
        IntervalTrigger(seconds=10),
        args=[settings],
        id="import_publications",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_email,
        IntervalTrigger(seconds=10),
        args=[settings],
        id="email_delivery",
        max_instances=1,
        coalesce=True,
    )
    for job_id, check in [
        ("escalation", escalate),
        ("action_overdue", notify_overdue_actions),
        ("data_source_watch", watch_data_sources),
    ]:
        scheduler.add_job(
            _run_check,
            IntervalTrigger(minutes=1),
            args=[check, settings],
            id=job_id,
            max_instances=1,
            coalesce=True,
        )
    if settings.equipment_sync_enabled and settings.equipment_sync_url:
        scheduler.add_job(
            _run_equipment,
            IntervalTrigger(seconds=settings.equipment_sync_interval_seconds),
            args=[settings],
            id="equipment_sync",
            max_instances=1,
            coalesce=True,
        )
    if settings.helpdesk_url:
        scheduler.add_job(
            _run_helpdesk,
            IntervalTrigger(seconds=settings.helpdesk_interval_seconds),
            args=[settings],
            id="helpdesk_sync",
            max_instances=1,
            coalesce=True,
        )
    _scheduler = scheduler
    return scheduler
