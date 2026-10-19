from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import replay as replay_service
from app.domain import replay_scenarios
from app.schemas.replay import (
    ReplayScenarioIn,
    ReplayState,
    ReplayStopIn,
    ReplayWeekIn,
    ScenarioCatalog,
)

router = APIRouter(prefix="/replay", tags=["replay"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
AdminDep = Annotated[Principal, Depends(require_min_role("admin"))]


def _state(session: Session, settings: Settings) -> ReplayState:
    return ReplayState.model_validate(replay_service.read_state(session, settings))


def _audit(session: Session, principal: Principal, action: str, run_id: str, detail: str) -> None:
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action=action,
        resource_type="replay",
        resource_id=run_id or "",
        detail=detail,
    )


@router.get("", response_model=ReplayState)
def replay_state(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> ReplayState:
    return _state(session, settings)


@router.get("/scenarios", response_model=ScenarioCatalog)
def replay_scenarios_catalog(settings: SettingsDep, _: ReaderDep) -> ScenarioCatalog:
    return replay_scenarios.load_catalog(settings)


@router.post("/week", response_model=ReplayState, status_code=status.HTTP_202_ACCEPTED)
def start_week(
    body: ReplayWeekIn, session: SessionDep, settings: SettingsDep, principal: AdminDep
) -> ReplayState:
    try:
        started = replay_service.start_week(
            settings, body.start, body.end, body.speed, body.simulate_dispatcher
        )
    except replay_service.ReplayError as error:
        raise HTTPException(error.status, error.detail) from None
    _audit(
        session,
        principal,
        "replay.start",
        started["run_id"],
        f"week {started['start']} — {started['end']}, speed={body.speed:g}, "
        f"simulate={body.simulate_dispatcher}",
    )
    return _state(session, settings)


@router.post("/scenario", response_model=ReplayState, status_code=status.HTTP_202_ACCEPTED)
def start_scenario(
    body: ReplayScenarioIn, session: SessionDep, settings: SettingsDep, principal: AdminDep
) -> ReplayState:
    try:
        started = replay_service.start_scenario(settings, body.id)
    except replay_service.ReplayError as error:
        raise HTTPException(error.status, error.detail) from None
    _audit(session, principal, "replay.scenario", started["run_id"], f"scenario {body.id}")
    return _state(session, settings)


@router.post("/stop", response_model=ReplayState)
def stop_replay(
    session: SessionDep,
    settings: SettingsDep,
    principal: AdminDep,
    body: ReplayStopIn | None = None,
) -> ReplayState:
    request = body or ReplayStopIn()
    try:
        stopped = replay_service.stop(settings, request.return_live)
    except replay_service.ReplayError as error:
        raise HTTPException(error.status, error.detail) from None
    _audit(
        session,
        principal,
        "replay.stop",
        stopped["run_id"],
        "return_live" if request.return_live else "stop",
    )
    return _state(session, settings)
