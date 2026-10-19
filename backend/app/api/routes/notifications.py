from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.models import Notification
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import notifications as service
from app.domain.email import Letter, build_email_provider, vena_link
from app.domain.scopes import Scope, ScopeDep, among
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
    scope: ScopeDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity: str | None = None,
    type_filter: Annotated[str | None, Query(alias="type")] = None,
    asset_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NotificationOut]:
    visible = (
        None
        if scope.channels is None
        else or_(Notification.asset_id.is_(None), among(Notification.asset_id, scope.channels))
    )
    items = service.list_notifications(
        session, status_filter, severity, type_filter, asset_id, limit, offset, visible
    )
    return [NotificationOut.model_validate(item) for item in items]


def _visible(session: Session, notification_id: str, scope: Scope) -> Notification:
    notification = service.get_notification(session, notification_id)
    if notification is None or (
        notification.asset_id is not None and not scope.has_channel(notification.asset_id)
    ):
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    return notification


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreate,
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
    scope: ScopeDep,
) -> NotificationOut:
    if payload.asset_id is not None and not scope.has_channel(payload.asset_id):
        raise HTTPException(status_code=404, detail="Объект не найден")
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
def get_notification(
    notification_id: str, session: SessionDep, _: ReaderDep, scope: ScopeDep
) -> NotificationOut:
    return NotificationOut.model_validate(_visible(session, notification_id, scope))


@router.patch("/{notification_id}", response_model=NotificationOut)
def patch_notification(
    notification_id: str,
    payload: NotificationPatch,
    session: SessionDep,
    principal: ActorDep,
    scope: ScopeDep,
) -> NotificationOut:
    notification = _visible(session, notification_id, scope)
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
    letter = Letter(
        kicker="Проверка",
        title="Проверочное письмо VENA",
        link=vena_link(settings.public_url, "/settings/notifications"),
        summary="Если письмо дошло, почтовый канал VENA настроен верно.",
    )
    try:
        provider.send(
            str(payload.recipient),
            "VENA · Проверка уведомлений",
            letter.text(),
            html=letter.html(),
        )
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Не удалось доставить письмо") from error
    return TestEmailResult(delivered=True, detail="Письмо принято почтовым сервером")
