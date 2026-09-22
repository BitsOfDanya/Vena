from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.domain import settings_store
from app.schemas.notifications import EmailStatus, NotificationSettings, NotificationSettingsUpdate

router = APIRouter(tags=["settings"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/settings/notifications", response_model=NotificationSettings)
def read_notification_settings(session: SessionDep, settings: SettingsDep) -> NotificationSettings:
    return settings_store.read_settings(session, settings)


@router.put("/settings/notifications", response_model=NotificationSettings)
def update_notification_settings(
    payload: NotificationSettingsUpdate, session: SessionDep, settings: SettingsDep
) -> NotificationSettings:
    return settings_store.write_settings(session, settings, payload)


@router.get("/integrations/email/status", response_model=EmailStatus)
def email_status(settings: SettingsDep) -> EmailStatus:
    if not settings.smtp_configured:
        return EmailStatus(configured=False, provider="none")
    address = settings.smtp_from
    local, _, domain = address.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "***"
    return EmailStatus(configured=True, provider="smtp", from_address=masked)
