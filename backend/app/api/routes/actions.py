from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.domain import actions as service
from app.schemas.actions import ActionCreate, ActionOut, ActionPatch, AssignRequest, ResultRequest

router = APIRouter(prefix="/actions", tags=["actions"])

SessionDep = Annotated[Session, Depends(get_session)]
ACTOR = "Duty engineer"


def _get(session: Session, action_id: str):
    action = service.get_action(session, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


def _out(action) -> ActionOut:
    return ActionOut.model_validate(service.to_dict(action))


@router.get("", response_model=list[ActionOut])
def list_actions(
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    asset_id: str | None = None,
) -> list[ActionOut]:
    return [_out(action) for action in service.list_actions(session, status_filter, asset_id)]


@router.post("", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def create_action(payload: ActionCreate, session: SessionDep) -> ActionOut:
    return _out(service.create_action(session, payload, ACTOR))


@router.get("/{action_id}", response_model=ActionOut)
def get_action(action_id: str, session: SessionDep) -> ActionOut:
    return _out(_get(session, action_id))


@router.patch("/{action_id}", response_model=ActionOut)
def patch_action(action_id: str, payload: ActionPatch, session: SessionDep) -> ActionOut:
    return _out(service.patch_action(session, _get(session, action_id), payload, ACTOR))


def _transition(session: Session, action_id: str, to_status: str, note: str = "") -> ActionOut:
    action = _get(session, action_id)
    try:
        return _out(service.transition(session, action, to_status, ACTOR, note))
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{action_id}/approve", response_model=ActionOut)
def approve_action(action_id: str, session: SessionDep) -> ActionOut:
    action = _get(session, action_id)
    try:
        return _out(service.approve(session, action, ACTOR))
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{action_id}/dismiss", response_model=ActionOut)
def dismiss_action(action_id: str, session: SessionDep) -> ActionOut:
    return _transition(session, action_id, "dismissed")


@router.post("/{action_id}/assign", response_model=ActionOut)
def assign_action(action_id: str, payload: AssignRequest, session: SessionDep) -> ActionOut:
    action = _get(session, action_id)
    try:
        return _out(service.assign(session, action, payload.assignee, ACTOR))
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{action_id}/start", response_model=ActionOut)
def start_action(action_id: str, session: SessionDep) -> ActionOut:
    return _transition(session, action_id, "in_progress")


@router.post("/{action_id}/wait", response_model=ActionOut)
def wait_action(action_id: str, session: SessionDep) -> ActionOut:
    return _transition(session, action_id, "waiting")


@router.post("/{action_id}/cancel", response_model=ActionOut)
def cancel_action(action_id: str, session: SessionDep) -> ActionOut:
    return _transition(session, action_id, "cancelled")


@router.post("/{action_id}/result", response_model=ActionOut)
def record_result(action_id: str, payload: ResultRequest, session: SessionDep) -> ActionOut:
    action = _get(session, action_id)
    try:
        return _out(service.complete(session, action, payload.outcome, payload.note, ACTOR))
    except service.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
