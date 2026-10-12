import asyncio
import time
from typing import Callable

import httpx

from .base import BaseClient

MAX_TITLES = 5
TITLE_TTL_S = 300
TITLE_BUDGET_S = 5.0
TITLE_CONCURRENCY = 8


class ArrClient(BaseClient):
    """Sonarr + Radarr share /api/v3."""

    def __init__(self, *args, clock: Callable[[], float] = time.monotonic, **kwargs):
        super().__init__(*args, **kwargs)
        self._clock = clock
        self._titles: dict[tuple[str, int], tuple[float, str | None]] = {}
        self._title_sem = asyncio.Semaphore(TITLE_CONCURRENCY)

    async def system_status(self) -> dict:
        return await self.get_json("/api/v3/system/status")

    async def health(self) -> list[dict]:
        return await self.get_json("/api/v3/health")

    async def diskspace(self) -> list[dict]:
        return await self.get_json("/api/v3/diskspace")

    async def queue(self) -> list[dict]:
        data = await self.get_json("/api/v3/queue", params={"pageSize": 200})
        return data.get("records", [])

    async def queue_page(self, limit: int) -> tuple[list[dict], int]:
        data = await self.get_json("/api/v3/queue", params={"pageSize": limit})
        return data.get("records", []), data.get("totalRecords", 0)

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

    async def commands(self) -> list[dict]:
        """Queued, running and recently finished commands (kept for minutes only)."""
        return await self.get_json("/api/v3/command")

    async def system_tasks(self) -> list[dict]:
        return await self.get_json("/api/v3/system/task")

    async def _title(self, kind: str, item_id: int) -> str | None:
        now = self._clock()
        hit = self._titles.get((kind, item_id))
        if hit and now - hit[0] < TITLE_TTL_S:
            return hit[1]
        try:
            async with self._title_sem:
                title = (await self.get_json(f"/api/v3/{kind}/{item_id}")).get("title")
        except (httpx.HTTPError, ValueError):  # deleted item or a bad reply: drop the title
            return None
        self._titles[(kind, item_id)] = (now, title)
        return title

    async def titles(self, kind: str, ids: list[int]) -> list[str]:
        """Titles for the first MAX_TITLES ids, in id order. Slow lookups are dropped after
        TITLE_BUDGET_S so a job poll never waits on every title."""
        tasks = [asyncio.ensure_future(self._title(kind, i)) for i in ids[:MAX_TITLES]]
        if not tasks:
            return []
        done, pending = await asyncio.wait(tasks, timeout=TITLE_BUDGET_S)
        for t in pending:
            t.cancel()
        return [t.result() for t in tasks if t in done and t.result()]
