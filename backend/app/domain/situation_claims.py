from collections.abc import Collection

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import Principal
from app.db.models import SituationClaim
from app.domain.system import now, situation_key, situations
from app.schemas.system import Situation

DUTY_NAME = "Дежурный инженер"


class ClaimTaken(Exception):
    def __init__(self, holder: str) -> None:
        super().__init__(holder)
        self.holder = holder


class ClaimForbidden(Exception):
    pass


def display_name(principal: Principal) -> str:
    return DUTY_NAME if principal.auth_method == "disabled" else principal.subject


def find(
    session: Session, settings: Settings, situation_id: str, objects: Collection[str] | None
) -> Situation | None:
    key = situation_key(situation_id)
    return next(
        (
            item
            for item in situations(session, settings, limit=10_000, objects=objects)
            if situation_key(item.id) == key
        ),
        None,
    )


def claim(
    session: Session, situation: Situation, principal: Principal
) -> tuple[SituationClaim, bool]:
    key = situation_key(situation.id)
    created = session.scalar(
        insert(SituationClaim)
        .values(
            situation_key=key,
            situation_id=situation.id,
            subject=principal.subject[:120],
            display_name=display_name(principal)[:120],
            claimed_at=now(),
        )
        .on_conflict_do_nothing(index_elements=["situation_key"])
        .returning(SituationClaim.situation_key)
    )
    record = session.get(SituationClaim, key, populate_existing=True)
    if record is None:
        raise ClaimTaken("")
    if record.subject != principal.subject[:120]:
        raise ClaimTaken(record.display_name)
    return record, created is not None


def release(session: Session, situation_id: str, principal: Principal) -> SituationClaim | None:
    record = session.get(SituationClaim, situation_key(situation_id))
    if record is None:
        return None
    if record.subject != principal.subject[:120] and principal.role != "admin":
        raise ClaimForbidden
    session.delete(record)
    session.flush()
    return record
