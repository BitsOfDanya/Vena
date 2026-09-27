from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import settings_store
from app.schemas.notifications import EmailStatus, NotificationSettings, NotificationSettingsUpdate

router = APIRouter(tags=["settings"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
WriterDep = Annotated[Principal, Depends(require_min_role("admin"))]


@router.get("/settings/notifications", response_model=NotificationSettings)
def read_notification_settings(
    session: SessionDep, settings: SettingsDep, _: ReaderDep
) -> NotificationSettings:
    return settings_store.read_settings(session, settings)


@router.put("/settings/notifications", response_model=NotificationSettings)
def update_notification_settings(
    payload: NotificationSettingsUpdate,
    session: SessionDep,
    settings: SettingsDep,
    principal: WriterDep,
) -> NotificationSettings:
    result = settings_store.write_settings(session, settings, payload)
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="settings.notifications.update",
        resource_type="settings",
        resource_id="notifications",
    )
    return result


@router.get("/integrations/email/status", response_model=EmailStatus)
def email_status(settings: SettingsDep, _principal: ReaderDep) -> EmailStatus:
    if not settings.smtp_configured:
        return EmailStatus(configured=False, provider="none")
    address = settings.smtp_from
    local, _, domain = address.partition("@")
    masked = f"{local[:2]}***@{domain}" if domain else "***"
    return EmailStatus(configured=True, provider="smtp", from_address=masked)
