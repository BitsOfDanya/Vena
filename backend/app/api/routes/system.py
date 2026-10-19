from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import situation_claims as claims
from app.domain import system as service
from app.domain.scopes import ScopeDep
from app.schemas.system import HealthComponents, Situation, SituationClaimOut, SystemNotice

router = APIRouter(tags=["system"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
ActorDep = Annotated[Principal, Depends(require_min_role("dispatcher"))]
SituationIdPath = Annotated[str, Path(min_length=1, max_length=255)]


@router.get("/system/notices", response_model=list[SystemNotice])
def system_notices(settings: SettingsDep, session: SessionDep, _: ReaderDep) -> list[SystemNotice]:
    return service.system_notices(settings, session)


@router.get("/system/components", response_model=HealthComponents)
def system_components(settings: SettingsDep, session: SessionDep, _: ReaderDep) -> HealthComponents:
    return service.health_components(settings, session)


@router.get("/situations", response_model=list[Situation])
def situations(
    session: SessionDep, settings: SettingsDep, _: ReaderDep, scope: ScopeDep
) -> list[Situation]:
    return service.situations(session, settings, objects=scope.objects)


@router.post("/situations/{situation_id:path}/claim", response_model=SituationClaimOut)
def claim_situation(
    situation_id: SituationIdPath,
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
    scope: ScopeDep,
) -> SituationClaimOut:
    situation = claims.find(session, settings, situation_id, scope.objects)
    if situation is None:
        raise HTTPException(status_code=404, detail="Ситуация не найдена или уже снята")
    try:
        record, created = claims.claim(session, situation, principal)
    except claims.ClaimTaken as error:
        holder = f": её ведёт {error.holder}" if error.holder else ""
        raise HTTPException(status_code=409, detail=f"Ситуация уже в работе{holder}") from error
    if created:
        audit_service.record(
            session,
            actor=principal.subject,
            role=principal.role,
            action="situation.claim",
            resource_type="situation",
            resource_id=record.situation_key[:80],
            detail=situation.title,
        )
    return SituationClaimOut(
        situation_id=situation.id,
        claimed_by=record.display_name,
        claimed_by_subject=record.subject,
        claimed_at=record.claimed_at,
    )


@router.delete("/situations/{situation_id:path}/claim", status_code=status.HTTP_204_NO_CONTENT)
def release_situation(
    situation_id: SituationIdPath, session: SessionDep, principal: ReaderDep
) -> Response:
    try:
        record = claims.release(session, situation_id, principal)
    except claims.ClaimForbidden as error:
        raise HTTPException(
            status_code=403, detail="Отпустить ситуацию может тот, кто её ведёт, или администратор"
        ) from error
    if record is None:
        raise HTTPException(status_code=404, detail="Ситуация никем не взята в работу")
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="situation.release",
        resource_type="situation",
        resource_id=record.situation_key[:80],
        detail=f"Вёл: {record.display_name}",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
