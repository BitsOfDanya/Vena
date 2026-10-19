from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

NotificationType = Literal["risk", "pattern", "action", "system", "integration"]
NotificationSeverity = Literal["info", "attention", "critical"]
NotificationStatus = Literal["new", "acknowledged", "resolved"]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: NotificationType
    severity: NotificationSeverity
    title: str
    description: str
    asset_id: str | None
    pattern_id: str | None
    action_id: str | None
    created_at: datetime
    status: NotificationStatus
    read_at: datetime | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class NotificationCreate(BaseModel):
    type: NotificationType
    severity: NotificationSeverity
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    asset_id: str | None = None
    pattern_id: str | None = None
    action_id: str | None = None
    dedup_key: str | None = None


class NotificationPatch(BaseModel):
    read: bool | None = None
    status: Literal["acknowledged", "resolved"] | None = None


class RecipientGroup(BaseModel):
    id: str
    name: str
    emails: list[EmailStr] = []
    enabled: bool = True


class NotificationRule(BaseModel):
    id: str
    trigger: Literal[
        "new_events",
        "alarm_event",
        "critical_risk",
        "risk_horizon_24h",
        "new_pattern",
        "action_overdue",
        "action_assigned",
        "data_source_unavailable",
    ]
    severity: NotificationSeverity
    recipients: list[str] = []
    channels: list[Literal["in_app", "email"]] = ["in_app"]
    cooldown_minutes: int = Field(default=240, ge=0, le=10080)
    enabled: bool = True


class DigestSettings(BaseModel):
    id: str = "morning_brief"
    name: str = "Утренняя сводка"
    enabled: bool = True
    hour: int = Field(default=8, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "Europe/Moscow"
    recipients: list[str] = []
    sections: list[str] = [
        "critical_risks",
        "new_patterns",
        "open_actions",
        "overdue_actions",
        "changes",
    ]

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            if value:
                ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Неизвестный часовой пояс") from error
        return value


class EscalationSettings(BaseModel):
    enabled: bool = True
    minutes: int = Field(default=30, ge=1, le=1440)
    recipients: list[str] = ["management"]


class ChannelState(BaseModel):
    id: Literal["in_app", "email", "webhook", "telegram", "teams"]
    name: str
    state: Literal["configured", "not_configured", "disabled"]
    available: bool
    detail: str


class NotificationSettings(BaseModel):
    channels: list[ChannelState] = []
    recipients: list[RecipientGroup] = []
    rules: list[NotificationRule] = []
    digest: DigestSettings = DigestSettings()
    escalation: EscalationSettings = EscalationSettings()


class NotificationSettingsUpdate(BaseModel):
    recipients: list[RecipientGroup] | None = None
    rules: list[NotificationRule] | None = None
    digest: DigestSettings | None = None
    escalation: EscalationSettings | None = None


class EmailStatus(BaseModel):
    configured: bool
    provider: Literal["smtp", "none"]
    from_address: str | None = None


class TestEmailRequest(BaseModel):
    recipient: EmailStr


class TestEmailResult(BaseModel):
    delivered: bool
    detail: str
