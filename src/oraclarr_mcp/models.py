from typing import Any, Literal
from pydantic import BaseModel

InstanceStatus = Literal["ok", "unreachable", "auth_failed", "error"]
Risk = Literal["read", "safe_write", "destructive"]
Domain = Literal["media", "downloads", "transcode", "library", "infra"]

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
