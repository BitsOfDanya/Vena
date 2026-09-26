from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SpatialStatus(BaseModel):
    configured: bool
    source: str | None = None
    feature_count: int = 0
    asset_count: int = 0
    updated_at: datetime | None = None


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


class WktPoint(BaseModel):
    asset_id: str = Field(min_length=1, max_length=32)
    wkt: str = Field(min_length=3, max_length=200)


class WktImport(BaseModel):
    points: list[WktPoint] = Field(min_length=1)
