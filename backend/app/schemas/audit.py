from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: datetime
    actor: str
    role: str
    action: str
    resource_type: str
    resource_id: str
    detail: str
    ip: str | None
