from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings
from app.db.session import SessionLocal
from app.domain import equipment, imports
from app.domain.digest import send_digest
from app.domain.email import build_email_provider
from app.domain.ingest import refresh_predictions
from app.domain.mail_queue import deliver_pending
from app.domain.predictions import get_prediction_source
from app.domain.settings_store import read_settings


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


def _run_publications(settings: Settings) -> None:
    with SessionLocal() as session:
        try:
            imports.publish_pending(session, settings)
        except equipment.RegistryError:
            session.rollback()


def _run_email(settings: Settings) -> None:
    with SessionLocal() as session:
        deliver_pending(session, build_email_provider(settings))


def build_scheduler(settings: Settings) -> BackgroundScheduler | None:
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
        CronTrigger(
            hour=digest.hour, minute=digest.minute, timezone=digest.timezone or settings.timezone
        ),
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
    if settings.equipment_sync_enabled and settings.equipment_sync_url:
        scheduler.add_job(
            _run_equipment,
            IntervalTrigger(seconds=settings.equipment_sync_interval_seconds),
            args=[settings],
            id="equipment_sync",
            max_instances=1,
            coalesce=True,
        )
    return scheduler
