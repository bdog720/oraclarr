from typing import Any, Literal
from pydantic import BaseModel

InstanceStatus = Literal["ok", "unreachable", "auth_failed", "error"]
Risk = Literal["read", "safe_write", "destructive"]
Domain = Literal["media", "downloads", "transcode", "library", "infra"]

# Arr-family instance types. Sportarr serves a Sonarr-compatible /api/v3, so it
# routes to ArrClient like its peers. Every arr selector reads this constant.
ARR_TYPES: tuple[str, ...] = ("sonarr", "radarr", "sportarr")

class InstanceResult(BaseModel):
    instance: str
    type: str
    status: InstanceStatus
    data: Any | None = None
    error: str | None = None

class MediaRef(BaseModel):
    title: str
    instance: str
    item_id: int | None = None
    tvdb_id: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
