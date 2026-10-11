from oraclarr_mcp.tools.diagnose import diagnose

class FakeArr:
    name="sonarr"; type="sonarr"
    async def lookup_library(self, term, media):
        return [{"title": "Show", "id": 7, "tvdbId": 111}] if term.lower() in "show" else []
    async def queue(self):
        return [{"title": "Show.S03E04", "seriesId": 7, "downloadId": "H1",
                 "trackedDownloadState": "downloading", "size": 100, "sizeleft": 50}]
    async def wanted_missing(self):
        return [{"title": "Show", "seriesId": 7}]

async def test_diagnose_reports_found_and_in_queue():
    res = await diagnose({"sonarr": FakeArr()}, title="Show")
    assert res["matches"][0]["instance"] == "sonarr"
    assert res["matches"][0]["in_library"] is True
    assert res["matches"][0]["in_queue"] is True
    assert res["matches"][0]["wanted"] is True

async def test_diagnose_no_match():
    res = await diagnose({"sonarr": FakeArr()}, title="Nonexistent")
    assert res["matches"] == []


import asyncio  # noqa: E402
import time  # noqa: E402


class FakeSportarr:
    name = "sportarr"; type = "sportarr"
    async def lookup_library(self, term, media):
        assert media == "series"
        return [{"title": "NBA", "id": 4}]
    async def queue(self):
        return [{"title": "Game 1", "seriesId": 4}]
    async def wanted_missing(self):
        return [{"title": "Game 2", "seriesId": 4}]


async def test_diagnose_sportarr_matches_by_series_id():
    res = await diagnose({"sportarr": FakeSportarr()}, title="NBA")
    m = res["matches"][0]
    assert m["in_queue"] is True
    assert m["wanted"] is True


class SlowArr(FakeArr):
    def __init__(self, name):
        self.name = name
    async def lookup_library(self, term, media):
        await asyncio.sleep(0.3)
        return await super().lookup_library(term, media)


async def test_diagnose_runs_instances_in_parallel():
    t0 = time.monotonic()
    res = await diagnose({"a": SlowArr("a"), "b": SlowArr("b")}, title="Show")
    assert time.monotonic() - t0 < 0.5
    assert {m["instance"] for m in res["matches"]} == {"a", "b"}


class BrokenQueue(FakeArr):
    name = "broken"
    async def queue(self):
        raise RuntimeError("queue down")


class BrokenLookup(FakeArr):
    name = "broken"
    async def lookup_library(self, term, media):
        raise RuntimeError("lookup down")


async def test_diagnose_reports_failing_instance_and_keeps_peers():
    res = await diagnose({"sonarr": FakeArr(), "broken": BrokenLookup()}, title="Show")
    assert [m["instance"] for m in res["matches"]] == ["sonarr"]
    assert res["errors"][0]["instance"] == "broken"
    assert res["errors"][0]["status"] == "error"


async def test_diagnose_queue_failure_keeps_match_with_unknown_queue_state():
    res = await diagnose({"broken": BrokenQueue()}, title="Show")
    m = res["matches"][0]
    assert m["in_library"] is True
    assert m["in_queue"] is None
    assert m["queue_error"] == "queue down"
    assert m["wanted"] is True
    assert res["errors"] == []


class ManyArr(FakeArr):
    async def lookup_library(self, term, media):
        return [{"title": f"Show {i}", "id": i} for i in range(30)]


async def test_diagnose_caps_matches_per_instance():
    res = await diagnose({"sonarr": ManyArr()}, title="Show")
    assert len(res["matches"]) == 20
    assert res["truncated"] is True
