from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field


class SpatialStatus(BaseModel):
    configured: bool
    source: str | None = None
    label: str | None = None
    imported: bool = False
    generated: bool = False
    feature_count: int = 0
    asset_count: int = 0
    collector_count: int = 0
    gallery_count: int = 0
    object_count: int = 0
    updated_at: datetime | None = None
    detail: str | None = None


class SpatialCollectionOut(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]
    properties: dict[str, Any] | None = None
    source: str
    updated_at: datetime | None = None


class GeoJsonImport(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]]
    properties: dict[str, Any] | None = None


class WktItem(BaseModel):
    id: str = Field(min_length=1, max_length=80, validation_alias=AliasChoices("id", "asset_id"))
    wkt: str = Field(min_length=5, max_length=2_000_000)
    kind: Literal["asset", "collector", "gallery"] | None = None
    object_id: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=200)


class WktImport(BaseModel):
    features: list[WktItem] = Field(
        min_length=1, max_length=200_000, validation_alias=AliasChoices("features", "points")
    )
