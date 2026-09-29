import json

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import SettingsRecord
from app.schemas.notifications import (
    ChannelState,
    DigestSettings,
    NotificationRule,
    NotificationSettings,
    NotificationSettingsUpdate,
    RecipientGroup,
)

SETTINGS_KEY = "notifications"

DEFAULT_RECIPIENTS = [
    RecipientGroup(id="dispatcher_team", name="Диспетчеры", emails=[], enabled=True),
    RecipientGroup(id="maintenance_team", name="Эксплуатация", emails=[], enabled=True),
    RecipientGroup(id="management", name="Руководство", emails=[], enabled=True),
]

DEFAULT_RULES = [
    NotificationRule(
        id="new_events",
        trigger="new_events",
        severity="info",
        recipients=["dispatcher_team"],
        channels=["in_app", "email"],
        cooldown_minutes=0,
    ),
    NotificationRule(
        id="alarm_event",
        trigger="alarm_event",
        severity="attention",
        recipients=["dispatcher_team", "maintenance_team"],
        channels=["in_app", "email"],
        cooldown_minutes=15,
    ),
    NotificationRule(
        id="critical_risk",
        trigger="critical_risk",
        severity="critical",
        recipients=["dispatcher_team"],
        channels=["in_app", "email"],
        cooldown_minutes=240,
    ),
    NotificationRule(
        id="risk_horizon_24h",
        trigger="risk_horizon_24h",
        severity="attention",
        recipients=["dispatcher_team", "maintenance_team"],
        channels=["in_app", "email"],
        cooldown_minutes=360,
    ),
    NotificationRule(
        id="new_pattern",
        trigger="new_pattern",
        severity="attention",
        recipients=["dispatcher_team"],
        channels=["in_app", "email"],
        cooldown_minutes=120,
    ),
    NotificationRule(
        id="action_overdue",
        trigger="action_overdue",
        severity="attention",
        recipients=["maintenance_team", "management"],
        channels=["in_app", "email"],
        cooldown_minutes=1440,
        enabled=False,
    ),
    NotificationRule(
        id="action_assigned",
        trigger="action_assigned",
        severity="info",
        recipients=["maintenance_team"],
        channels=["in_app"],
        cooldown_minutes=0,
    ),
    NotificationRule(
        id="data_source_unavailable",
        trigger="data_source_unavailable",
        severity="critical",
        recipients=["dispatcher_team", "management"],
        channels=["in_app", "email"],
        cooldown_minutes=60,
    ),
]


def channel_states(settings: Settings) -> list[ChannelState]:
    return [
        ChannelState(
            id="in_app",
            name="В приложении",
            state="configured",
            available=True,
            detail="Центр уведомлений VENA",
        ),
        ChannelState(
            id="email",
            name="Email",
            state="configured" if settings.smtp_configured else "not_configured",
            available=True,
            detail="SMTP настроен на сервере" if settings.smtp_configured else "SMTP не настроен",
        ),
        ChannelState(
            id="webhook", name="Webhook", state="disabled", available=False, detail="Планируется"
        ),
        ChannelState(
            id="telegram", name="Telegram", state="disabled", available=False, detail="Планируется"
        ),
        ChannelState(
            id="teams",
            name="Microsoft Teams",
            state="disabled",
            available=False,
            detail="Планируется",
        ),
    ]


def _stored(session: Session) -> dict:
    record = session.get(SettingsRecord, SETTINGS_KEY)
    if record is None:
        return {}
    return json.loads(record.value)


def read_settings(session: Session, settings: Settings) -> NotificationSettings:
    stored = _stored(session)
    digest = (
        DigestSettings(**stored["digest"])
        if "digest" in stored
        else DigestSettings(
            recipients=["management", "dispatcher_team"], timezone=settings.timezone
        )
    )
    return NotificationSettings(
        channels=channel_states(settings),
        recipients=[RecipientGroup(**item) for item in stored["recipients"]]
        if "recipients" in stored
        else DEFAULT_RECIPIENTS,
        rules=[NotificationRule(**item) for item in stored["rules"]]
        if "rules" in stored
        else DEFAULT_RULES,
        digest=digest,
    )


def write_settings(
    session: Session, settings: Settings, update: NotificationSettingsUpdate
) -> NotificationSettings:
    current = read_settings(session, settings)
    payload = {
        "recipients": [
            item.model_dump(mode="json")
            for item in (update.recipients if update.recipients is not None else current.recipients)
        ],
        "rules": [
            item.model_dump(mode="json")
            for item in (update.rules if update.rules is not None else current.rules)
        ],
        "digest": (update.digest or current.digest).model_dump(mode="json"),
    }
    record = session.get(SettingsRecord, SETTINGS_KEY)
    if record is None:
        session.add(SettingsRecord(key=SETTINGS_KEY, value=json.dumps(payload)))
    else:
        record.value = json.dumps(payload)
    session.flush()
    return read_settings(session, settings)
