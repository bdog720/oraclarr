import asyncio
import time
from typing import Callable

import httpx

from ..budget import remaining
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

    async def items(self, kind: str) -> list[dict]:
        return await self.get_json(f"/api/v3/{kind}")

    async def item(self, kind: str, item_id: int) -> dict | None:
        try:
            return await self.get_json(f"/api/v3/{kind}/{item_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def rename_preview(self, kind: str, item_id: int) -> list[dict]:
        key = "seriesId" if kind == "series" else "movieId"
        return await self.get_json("/api/v3/rename", params={key: item_id})

    async def custom_formats(self) -> list[dict]:
        return await self.get_json("/api/v3/customformat")

    async def quality_profiles(self) -> list[dict]:
        if self.type == "sportarr":
            return await self._sportarr_quality_profiles()
        return await self.get_json("/api/v3/qualityprofile")

    async def _sportarr_quality_profiles(self) -> list[dict]:
        # Sportarr's /api/v3/qualityprofile omits formatItems and the format-score
        # fields. The native path has them, keyed formatId with format null, so the
        # name comes from the v3 custom formats. Output is the Sonarr v3 shape.
        profiles, formats = await asyncio.gather(
            self.get_json("/api/qualityprofile"), self.custom_formats())
        names = {f.get("id"): f.get("name") for f in formats}
        return [{
            "id": p.get("id"),
            "name": p.get("name"),
            "cutoff": p.get("cutoffQuality"),
            "upgradeAllowed": p.get("upgradesAllowed"),
            "minFormatScore": p.get("minFormatScore"),
            "cutoffFormatScore": p.get("cutoffFormatScore"),
            "formatItems": [{"format": f.get("formatId"), "name": names.get(f.get("formatId")),
                             "score": f.get("score")} for f in p.get("formatItems") or []],
        } for p in profiles]

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
                reply = await self.get_json(f"/api/v3/{kind}/{item_id}")
        except Exception:  # noqa: BLE001 - titles are decoration; one bad id never fails a row
            return None
        title = reply.get("title") if isinstance(reply, dict) else None
        self._titles[(kind, item_id)] = (now, title)
        return title

    async def titles(self, kind: str, ids: list[int]) -> list[str]:
        """Titles for the first MAX_TITLES ids, in id order. Slow lookups are dropped after
        TITLE_BUDGET_S so a job poll never waits on every title."""
        tasks = [asyncio.ensure_future(self._title(kind, i)) for i in ids[:MAX_TITLES]]
        if not tasks:
            return []
        budget = TITLE_BUDGET_S
        left = remaining()
        if left is not None:  # leave the tool time to return the commands it already has
            budget = max(0.0, min(budget, left - 0.5))
        try:
            done, _ = await asyncio.wait(tasks, timeout=budget)
        finally:  # also when the caller is cancelled: free the semaphore slots
            for t in tasks:
                if not t.done():
                    t.cancel()
        return [t.result() for t in tasks if t in done and t.result()]
