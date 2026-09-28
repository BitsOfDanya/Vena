from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings
from app.db.session import SessionLocal
from app.domain.digest import send_digest
from app.domain.email import build_email_provider
from app.domain.ingest import refresh_predictions
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
    return scheduler
