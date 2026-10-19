from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import actions as service
from app.domain import audit as audit_service
from app.domain import helpdesk
from app.domain.notifications import notify_action
from app.domain.scopes import Scope, ScopeDep, get_scope
from app.schemas.actions import (
    ActionCreate,
    ActionOut,
    ActionPatch,
    AssignRequest,
    DismissRequest,
    ResultRequest,
)


def _in_scope(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    scope: Annotated[Scope, Depends(get_scope)],
) -> None:
    action_id = request.path_params.get("action_id")
    action = service.get_action(session, action_id) if action_id else None
    if action is not None and not scope.has_channel(action.asset_id):
        raise HTTPException(status_code=404, detail="Работа не найдена")


router = APIRouter(prefix="/actions", tags=["actions"], dependencies=[Depends(_in_scope)])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ActorDep = Annotated[Principal, Depends(require_min_role("dispatcher"))]
ReaderDep = Annotated[Principal, Depends(get_principal)]


def _get(session: Session, action_id: str):
    action = service.get_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    return action


def _out(action) -> ActionOut:
    return ActionOut.model_validate(service.to_dict(action))


def _audit(
    session: Session,
    principal: Principal,
    action_name: str,
    resource_id: str,
    detail: str = "",
) -> None:
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action=action_name,
        resource_type="action",
        resource_id=resource_id,
        detail=detail,
    )


@router.get("", response_model=list[ActionOut])
def list_actions(
    session: SessionDep,
    _: ReaderDep,
    scope: ScopeDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    asset_id: str | None = None,
) -> list[ActionOut]:
    return [
        _out(action)
        for action in service.list_actions(session, status_filter, asset_id)
        if scope.has_channel(action.asset_id)
    ]


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def create_action(
    payload: ActionCreate,
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
    scope: ScopeDep,
) -> ActionOut:
    if not scope.has_channel(payload.asset_id):
        raise HTTPException(status_code=404, detail="Объект не найден")
    action = service.create_action(session, payload, principal.subject)
    _audit(session, principal, "action.create", action.id, payload.asset_id)
    if payload.notify_channels and action.assignee:
        notify_action(
            session, settings, action, "action_assigned", channels=payload.notify_channels
        )
    if action.status == "planned":
        helpdesk.submit(session, settings, action)
    return _out(action)


@router.get("/{action_id}", response_model=ActionOut)
def get_action(action_id: str, session: SessionDep, _: ReaderDep) -> ActionOut:
    return _out(_get(session, action_id))


@router.patch("/{action_id}", response_model=ActionOut)
def patch_action(
    action_id: str,
    payload: ActionPatch,
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
) -> ActionOut:
    action = _get(session, action_id)
    previous = action.assignee
    action = service.patch_action(session, action, payload, principal.subject)
    _audit(session, principal, "action.patch", action.id)
    if payload.assignee and payload.assignee != previous:
        notify_action(session, settings, action, "action_assigned")
    return _out(action)


def _transition(
    session: Session, action_id: str, to_status: str, principal: Principal, note: str = ""
) -> ActionOut:
    action = _get(session, action_id)
    try:
        updated = service.transition(session, action, to_status, principal.subject, note)
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _audit(session, principal, f"action.{to_status}", action_id)
    return _out(updated)


@router.post("/{action_id}/approve", response_model=ActionOut)
def approve_action(
    action_id: str, session: SessionDep, settings: SettingsDep, principal: ActorDep
) -> ActionOut:
    action = _get(session, action_id)
    try:
        updated = service.approve(session, action, principal.subject)
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _audit(session, principal, "action.approve", action_id)
    helpdesk.submit(session, settings, updated)
    return _out(updated)


@router.post("/{action_id}/dismiss", response_model=ActionOut)
def dismiss_action(
    action_id: str,
    session: SessionDep,
    principal: ActorDep,
    payload: DismissRequest | None = None,
) -> ActionOut:
    decision = payload or DismissRequest()
    action = _get(session, action_id)
    try:
        updated = service.dismiss(
            session, action, decision.reason, decision.note, principal.subject
        )
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _audit(session, principal, "action.dismissed", action_id, decision.reason)
    return _out(updated)


@router.post("/{action_id}/assign", response_model=ActionOut)
def assign_action(
    action_id: str,
    payload: AssignRequest,
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
) -> ActionOut:
    action = _get(session, action_id)
    try:
        updated = service.assign(session, action, payload.assignee, principal.subject)
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _audit(session, principal, "action.assign", action_id, payload.assignee)
    notify_action(
        session,
        settings,
        updated,
        "action_assigned",
        channels=("in_app", "email") if payload.notify else None,
    )
    return _out(updated)


@router.post("/{action_id}/start", response_model=ActionOut)
def start_action(action_id: str, session: SessionDep, principal: ActorDep) -> ActionOut:
    return _transition(session, action_id, "in_progress", principal)


@router.post("/{action_id}/wait", response_model=ActionOut)
def wait_action(action_id: str, session: SessionDep, principal: ActorDep) -> ActionOut:
    return _transition(session, action_id, "waiting", principal)


@router.post("/{action_id}/cancel", response_model=ActionOut)
def cancel_action(action_id: str, session: SessionDep, principal: ActorDep) -> ActionOut:
    return _transition(session, action_id, "cancelled", principal)


@router.post("/{action_id}/result", response_model=ActionOut)
def record_result(
    action_id: str, payload: ResultRequest, session: SessionDep, principal: ActorDep
) -> ActionOut:
    action = _get(session, action_id)
    try:
        updated = service.complete(
            session, action, payload.outcome, payload.note, principal.subject
        )
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _audit(session, principal, "action.result", action_id, payload.outcome)
    return _out(updated)
