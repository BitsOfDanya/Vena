from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import require_dispatcher
from app.core.config import Settings, get_settings
from app.db.session import get_session
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
DispatcherDep = Annotated[object, Depends(require_dispatcher)]

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    session: SessionDep,
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
    background: BackgroundTasks,
    _dispatcher: DispatcherDep,
) -> NotificationOut:
    notification = service.create_notification(session, payload)
    trigger = (
        "critical_risk"
        if payload.severity == "critical"
        else "new_pattern"
        if payload.type == "pattern"
        else None
    )
    if trigger:
        provider = build_email_provider(settings)
        background.add_task(_dispatch, notification.id, trigger)
        service.dispatch(session, settings, provider, notification, trigger)
    return NotificationOut.model_validate(notification)


def _dispatch(notification_id: str, trigger: str) -> None:
    return None


@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(notification_id: str, session: SessionDep) -> NotificationOut:
    notification = service.get_notification(session, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return NotificationOut.model_validate(notification)


@router.patch("/{notification_id}", response_model=NotificationOut)
def patch_notification(
    notification_id: str,
    payload: NotificationPatch,
    session: SessionDep,
    _dispatcher: DispatcherDep,
) -> NotificationOut:
    notification = service.get_notification(session, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="notification not found")
    try:
        updated = service.patch_notification(session, notification, payload)
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return NotificationOut.model_validate(updated)


@router.post("/test", response_model=TestEmailResult)
def send_test_notification(
    payload: TestEmailRequest, settings: SettingsDep, _dispatcher: DispatcherDep
) -> TestEmailResult:
    provider = build_email_provider(settings)
    if not provider.configured:
        raise HTTPException(status_code=409, detail="email provider is not configured")
    try:
        provider.send(str(payload.recipient), "VENA · Test notification", "VENA test notification.")
    except Exception as error:  # noqa: BLE001 - reported to the caller
        raise HTTPException(status_code=502, detail=f"delivery failed: {error}") from error
    return TestEmailResult(delivered=True, detail="sent")
