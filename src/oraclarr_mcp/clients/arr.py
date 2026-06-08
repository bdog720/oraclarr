from typing import Any
from .base import BaseClient

class ArrClient(BaseClient):
    """Sonarr + Radarr share /api/v3."""

    async def system_status(self) -> dict:
        return await self.get_json("/api/v3/system/status")

    async def health(self) -> list[dict]:
        return await self.get_json("/api/v3/health")

    async def diskspace(self) -> list[dict]:
        return await self.get_json("/api/v3/diskspace")

    async def queue(self) -> list[dict]:
        data = await self.get_json("/api/v3/queue", params={"pageSize": 200})
        return data.get("records", [])

    async def history(self, limit: int = 30) -> list[dict]:
        data = await self.get_json("/api/v3/history",
                                   params={"pageSize": limit, "sortKey": "date", "sortDirection": "descending"})
        return data.get("records", [])

    async def wanted_missing(self) -> list[dict]:
        data = await self.get_json("/api/v3/wanted/missing", params={"pageSize": 200})
        return data.get("records", [])

    async def wanted_cutoff(self) -> list[dict]:
        data = await self.get_json("/api/v3/wanted/cutoff", params={"pageSize": 200})
        return data.get("records", [])

    async def custom_formats(self) -> list[dict]:
        return await self.get_json("/api/v3/customformat")

    async def quality_profiles(self) -> list[dict]:
        return await self.get_json("/api/v3/qualityprofile")

    async def release_profiles(self) -> list[dict]:
        return await self.get_json("/api/v3/releaseprofile")

    async def lookup_library(self, term: str, media: str) -> list[dict]:
        items = await self.get_json(f"/api/v3/{media}")
        t = term.lower()
        return [i for i in items if t in i.get("title", "").lower()]
