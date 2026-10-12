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


from oraclarr_mcp.tools import library  # noqa: E402


class FakeJf:
    type = "jellyfin"

    def __init__(self, name, item):
        self.name, self.item = name, item

    async def search_items(self, term, limit): return [self.item] * limit, 10**6
    async def recent_items(self, limit): return [self.item] * limit, 10**6


def _jf(item):
    return {f"jellyfin{i}": FakeJf(f"jellyfin{i}", item) for i in range(2)}


async def test_max_library_search_and_recent_fit_under_cap():
    # Live search rows are ~250 B; pad to 600 B for long paths, two Jellyfin servers.
    item = _padded(library.search_row, {
        "Name": "N", "Type": "Series", "ProductionYear": 2018, "Path": "/tv/N",
        "DateCreated": "2026-01-01T00:00:00Z",
        "ProviderIds": {"Tvdb": "1", "Tmdb": "2", "Imdb": "tt3"}}, "Path", 600)
    clients = _jf(item)

    async def search(limit):
        return await library.get_library(clients, None, "n", limit)

    async def recent(limit):
        return await library.get_library(clients, "recent", None, limit)

    for tool in (search, recent):
        _assert_full_and_ok(await _run(tool), library.MAX_LIMIT)


from oraclarr_mcp.tools import transcodes  # noqa: E402


async def test_max_transcodes_fits_under_cap():
    # Live: status ~160 B, nodes ~12 KB compact; staged _id paths ~200 B (pad to 400).
    staged_item = {"_id": "/media/" + "p" * 400, "status": "processing",
                   "workerType": "transcodegpu", "nodeID": "node1", "start": 1791756922182,
                   "flowPluginHandler": {"blob": "x" * 55_000}}

    class Tdarr:
        name = "tdarr"; type = "tdarr"
        async def status(self): return {"status": "x" * 160}
        async def nodes(self): return {"n1": {"blob": "y" * 12_500}}
        async def staged(self): return [staged_item] * 1000

    async def tool(limit):
        return await transcodes.get_transcodes({"tdarr": Tdarr()}, limit)

    out = await _run(tool)
    assert isinstance(out, list), out
    assert out[0]["status"] == "ok"
    assert len(out[0]["data"]["staged"]) == transcodes.MAX_LIMIT


from oraclarr_mcp.tools import cleanup  # noqa: E402


async def test_max_cleanup_strikes_fit_under_cap():
    item = _padded(cleanup.strike_row, {
        "downloadId": "a" * 40, "title": "T", "totalStrikes": 9,
        "strikesByType": {"Stalled": 3, "SlowSpeed": 3, "FailedImport": 3},
        "firstStrikeAt": "2026-10-11T10:00:00.0000000+00:00",
        "latestStrikeAt": "2026-10-12T10:00:00.0000000+00:00",
        "isMarkedForRemoval": False, "isRemoved": False, "hasDryRunStrikes": False},
        "title", 500)

    class Cl:
        type = "cleanuparr"

        def __init__(self, name):
            self.name = name

        async def strikes(self, page_size):
            return [item] * page_size, 10**6

    clients = {f"cl{i}": Cl(f"cl{i}") for i in range(2)}

    async def tool(limit):
        return await cleanup.get_cleanup(clients, "strikes", limit)

    _assert_full_and_ok(await _run(tool), cleanup.MAX_LIMIT)


from oraclarr_mcp.tools import queues  # noqa: E402


async def test_max_queue_with_qbit_and_strikes_fits_under_cap():
    title = "T" * 150  # long release names reach ~150 characters
    rec = {"title": title, "downloadId": "A" * 40, "status": "downloading",
           "trackedDownloadState": "downloading", "size": 10**10, "sizeleft": 3 * 10**9}

    class Arr:
        name = "sonarr"; type = "sonarr"
        async def queue_page(self, limit): return [rec] * limit, 10**6

    class Qbit:
        name = "qbit"; type = "qbittorrent"
        async def torrents(self):
            return [{"hash": "a" * 40, "state": "stalledDL", "progress": 0.7123}]

    class Cl:
        name = "cleanuparr"; type = "cleanuparr"
        async def strikes(self, page_size):
            return [{"downloadId": "a" * 40, "totalStrikes": 12,
                     "strikesByType": {"Stalled": 4, "SlowSpeed": 4, "FailedImport": 4},
                     "isMarkedForRemoval": True, "hasDryRunStrikes": False}], 1

    clients = {"sonarr": Arr(), "qbit": Qbit(), "cleanuparr": Cl()}

    async def tool(limit):
        return await queues.get_queues(clients, None, limit)

    out = await _run(tool)
    assert isinstance(out, dict) and "items" in out, out
    assert len(out["items"]) == queues.MAX_LIMIT


from oraclarr_mcp.tools import host  # noqa: E402


async def test_max_host_datasets_fit_under_cap():
    d = {"id": "tank/" + "d" * 120, "used": {"parsed": 10**12}, "available": {"parsed": 10**12},
         "quota": {"parsed": 10**12}}

    class Tn:
        name = "truenas"; type = "truenas"
        async def datasets(self): return [d] * 1000

    async def tool(limit):
        return await host.get_host({"truenas": Tn()}, "datasets", limit)

    _assert_full_and_ok(await _run(tool), host.MAX_LIMIT)
