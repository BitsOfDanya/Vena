from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings
from app.db.session import SessionLocal
from app.domain.digest import send_digest
from app.domain.email import build_email_provider
from app.domain.settings_store import read_settings


def _run_digest(settings: Settings) -> None:
    session = SessionLocal()
    try:
        send_digest(session, settings, build_email_provider(settings))
        session.commit()
    finally:
        session.close()


def build_scheduler(settings: Settings) -> BackgroundScheduler | None:
    if not settings.digest_enabled:
        return None
    session = SessionLocal()
    try:
        digest = read_settings(session, settings).digest
    finally:
        session.close()
    scheduler = BackgroundScheduler(timezone=digest.timezone or settings.timezone)
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
