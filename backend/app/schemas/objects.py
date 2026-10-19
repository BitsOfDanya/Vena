from pydantic import BaseModel, ConfigDict, Field


class ObjectIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    object_id: str = Field(min_length=1, max_length=64, pattern=r"^[0-9A-Za-z_.-]+$")
    level: int = Field(ge=1, le=3)
    parent: str = Field(default="", max_length=64)
    object_kind: str = Field(default="", max_length=40)
    title: str = Field(min_length=1, max_length=200)


class ObjectLeaf(BaseModel):
    id: str
    name: str
    kind: str = ""
    channels: int = 0


class ComplexNode(BaseModel):
    id: str
    name: str
    channels: int = 0
    objects: list[ObjectLeaf] = []


class DistrictNode(BaseModel):
    id: str
    name: str
    channels: int = 0
    complexes: list[ComplexNode] = []


class ObjectTree(BaseModel):
    available: bool
    districts: list[DistrictNode] = []
    unassigned: list[ObjectLeaf] = []
