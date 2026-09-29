from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EquipmentIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    asset_id: str = Field(min_length=1, max_length=32)
    external_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    object_id: str = Field(min_length=1, max_length=80)
    section: str = Field(default="", max_length=120)
    equipment_type: str = Field(default="", max_length=80)
    tag: str = Field(default="", max_length=200)
    system_type: str = Field(default="", max_length=120)
    manufacturer: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=120)
    serial_number: str = Field(default="", max_length=120)
    installed_on: date | None = None
    status: Literal["active", "maintenance", "retired"] = "active"


class EquipmentOut(EquipmentIn):
    model_config = ConfigDict(from_attributes=True)
    source: str
    updated_at: datetime
