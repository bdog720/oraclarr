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

    async def history_page(self, limit: int) -> tuple[list[dict], int]:
        """Newest-first history page. include* attach the parent title for projection."""
        data = await self.get_json("/api/v3/history", params={
            "pageSize": limit, "sortKey": "date", "sortDirection": "descending",
            "includeSeries": "true", "includeMovie": "true"})
        return data.get("records", []), data.get("totalRecords", 0)

    async def item_history(self, item_id: int, media: str) -> list[dict]:
        """Per-item grab/import history. Sonarr: series?seriesId; Radarr: movie?movieId."""
        param = "seriesId" if media == "series" else "movieId"
        return await self.get_json(f"/api/v3/history/{media}", params={param: item_id})

    async def calendar(self, start: str, end: str) -> list[dict]:
        """Date-bounded upcoming items. Sonarr/Sportarr return episodes, Radarr movies.

        includeSeries attaches the parent show/league; Radarr ignores it.
        """
        return await self.get_json("/api/v3/calendar", params={
            "start": start, "end": end, "includeSeries": "true"})

    async def wanted_missing(self) -> list[dict]:
        data = await self.get_json("/api/v3/wanted/missing", params={"pageSize": 200})
        return data.get("records", [])

    async def wanted_page(self, kind: str, limit: int) -> tuple[list[dict], int]:
        """kind is "missing" or "cutoff"."""
        data = await self.get_json(f"/api/v3/wanted/{kind}", params={
            "pageSize": limit, "includeSeries": "true"})
        return data.get("records", []), data.get("totalRecords", 0)

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
