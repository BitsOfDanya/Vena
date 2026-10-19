from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal
from app.db.session import get_session
from app.domain import journal as journal_service
from app.domain.actions import DISMISS_REASONS
from app.domain.scopes import ScopeDep
from app.schemas.journal import DecisionReason, JournalEntry, JournalSummary

router = APIRouter(prefix="/journal", tags=["journal"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]


@router.get("", response_model=list[JournalEntry])
def list_journal(
    session: SessionDep,
    settings: SettingsDep,
    _: ReaderDep,
    scope: ScopeDep,
    scenario: str | None = None,
    decision: str | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[JournalEntry]:
    return journal_service.entries(session, settings, scenario, decision, limit, scope.channels)


@router.get("/summary", response_model=JournalSummary)
def journal_summary(
    session: SessionDep, settings: SettingsDep, _: ReaderDep, scope: ScopeDep
) -> JournalSummary:
    rows = journal_service.entries(session, settings, limit=100_000, channels=scope.channels)
    return journal_service.summary(rows)


@router.get("/reasons", response_model=list[DecisionReason])
def decision_reasons(_: ReaderDep) -> list[DecisionReason]:
    return [
        DecisionReason(code=code, label=label, outcome=outcome)
        for code, (label, outcome) in DISMISS_REASONS.items()
    ]
