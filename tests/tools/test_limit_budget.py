"""The largest valid `limit` must fit under the default output cap.

Uses the largest projected row sizes seen on the live stack on 2026-10-12 and
the four arr instances that stack runs. If a projection grows, these fail.
"""
import json

from oraclarr_mcp.call_guard import guarded
from oraclarr_mcp.config import ServerSettings
from oraclarr_mcp.redact import Redactor
from oraclarr_mcp.tools import history, search, upcoming, wanted

CAP = ServerSettings().max_output_bytes
ARR = [("sonarr", "sonarr"), ("sonarr-anime", "sonarr"), ("radarr", "radarr"),
       ("sportarr", "sportarr")]
LIVE_MAX_ROW = {"history": 507, "search": 413, "wanted": 225, "upcoming": 178}


def _padded(project, raw: dict, field: str, target: int) -> dict:
    size = len(json.dumps(project(raw)))
    return dict(raw, **{field: raw[field] + "x" * max(0, target - size)})


class Fake:
    def __init__(self, name, type, rec):
        self.name, self.type, self.rec = name, type, rec
    async def history_page(self, limit): return [self.rec] * limit, 10**6
    async def wanted_page(self, kind, limit): return [self.rec] * limit, 10**6
    async def lookup_library(self, term, media): return [self.rec] * 1000
    async def calendar(self, start, end): return [self.rec] * 1000


def _clients(rec):
    return {n: Fake(n, t, rec) for n, t in ARR}


async def _run(tool):
    w = guarded("t", tool, budget_s=5, max_bytes=CAP, redactor=Redactor([]))
    return await w(limit=10**6)


def _assert_full_and_ok(out, max_limit):
    assert isinstance(out, list), out
    assert all(r["status"] == "ok" and len(r["data"]) == max_limit for r in out)


async def test_max_history_fits_under_cap():
    rec = _padded(history._event, {
        "date": "2026-10-11T10:00:00Z", "eventType": "grabbed", "sourceTitle": "S",
        "series": {"title": "T"}, "quality": {"quality": {"name": "WEBDL-1080p"}},
        "customFormatScore": 1, "downloadId": "D"}, "sourceTitle", LIVE_MAX_ROW["history"])
    clients = _clients(rec)

    async def tool(limit):
        return await history.get_history(clients, None, limit)

    _assert_full_and_ok(await _run(tool), history.MAX_LIMIT)


async def test_max_search_fits_under_cap():
    rec = _padded(search._item, {
        "title": "T", "year": 2020, "tvdbId": 1, "tmdbId": 2, "imdbId": "tt1",
        "monitored": True, "status": "continuing", "path": "/tv/T",
        "statistics": {"sizeOnDisk": 10**10, "episodeFileCount": 100, "episodeCount": 100}},
        "path", LIVE_MAX_ROW["search"])
    clients = _clients(rec)

    async def tool(limit):
        return await search.search_media(clients, "t", limit)

    _assert_full_and_ok(await _run(tool), search.MAX_LIMIT)


async def test_max_wanted_fits_under_cap():
    rec = _padded(lambda r: wanted._wanted(r, "missing"), {
        "title": "T", "seasonNumber": 1, "episodeNumber": 1,
        "airDateUtc": "2026-10-01T00:00:00Z", "monitored": True, "series": {"title": "S"}},
        "title", LIVE_MAX_ROW["wanted"])
    clients = _clients(rec)

    async def tool(limit):
        return await wanted.get_wanted(clients, None, limit)

    _assert_full_and_ok(await _run(tool), wanted.MAX_LIMIT)


async def test_max_upcoming_fits_under_cap():
    rec = _padded(lambda r: upcoming._normalise(r, "2026-01-01", "2026-12-31"), {
        "title": "T", "airDateUtc": "2026-10-12T00:00:00Z", "monitored": True,
        "hasFile": False, "series": {"title": "S"}}, "title", LIVE_MAX_ROW["upcoming"])
    clients = _clients(rec)

    async def tool(limit):
        return await upcoming.get_upcoming(clients, None, 7, limit)

    _assert_full_and_ok(await _run(tool), upcoming.MAX_LIMIT)
