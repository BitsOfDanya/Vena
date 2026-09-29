from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import notifications as service
from app.domain.email import build_email_provider
from app.schemas.notifications import (
    NotificationCreate,
    NotificationOut,
    NotificationPatch,
    TestEmailRequest,
    TestEmailResult,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
ActorDep = Annotated[Principal, Depends(require_min_role("dispatcher"))]


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    session: SessionDep,
    _: ReaderDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity: str | None = None,
    type_filter: Annotated[str | None, Query(alias="type")] = None,
    asset_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NotificationOut]:
    items = service.list_notifications(
        session, status_filter, severity, type_filter, asset_id, limit, offset
    )
    return [NotificationOut.model_validate(item) for item in items]


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreate,
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
) -> NotificationOut:
    notification = service.create_notification(session, payload)
    trigger = (
        "critical_risk"
        if payload.severity == "critical"
        else "new_pattern"
        if payload.type == "pattern"
        else "alarm_event"
        if payload.severity == "attention"
        else "new_events"
    )
    if trigger:
        provider = build_email_provider(settings)
        service.dispatch(session, settings, provider, notification, trigger)
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="notification.create",
        resource_type="notification",
        resource_id=notification.id,
    )
    return NotificationOut.model_validate(notification)


@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(notification_id: str, session: SessionDep, _: ReaderDep) -> NotificationOut:
    notification = service.get_notification(session, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    return NotificationOut.model_validate(notification)


@router.patch("/{notification_id}", response_model=NotificationOut)
def patch_notification(
    notification_id: str,
    payload: NotificationPatch,
    session: SessionDep,
    principal: ActorDep,
) -> NotificationOut:
    notification = service.get_notification(session, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    try:
        updated = service.patch_notification(session, notification, payload)
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="notification.patch",
        resource_type="notification",
        resource_id=notification_id,
        detail=payload.status or "",
    )
    return NotificationOut.model_validate(updated)


@router.post("/test", response_model=TestEmailResult)
def send_test_notification(
    payload: TestEmailRequest,
    settings: SettingsDep,
    _: Annotated[Principal, Depends(require_min_role("admin"))],
) -> TestEmailResult:
    provider = build_email_provider(settings)
    if not provider.configured:
        raise HTTPException(status_code=409, detail="Отправка электронной почты не настроена")
    try:
        provider.send(
            str(payload.recipient), "VENA · Проверка уведомлений", "Проверочное письмо VENA."
        )
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Не удалось доставить письмо") from error
    return TestEmailResult(delivered=True, detail="Письмо принято почтовым сервером")
