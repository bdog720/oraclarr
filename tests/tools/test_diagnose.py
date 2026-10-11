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
        return [{"title": "Example League", "id": 4}]
    async def queue(self):
        return [{"title": "Game 1", "seriesId": 4}]
    async def wanted_missing(self):
        return [{"title": "Game 2", "seriesId": 4}]


async def test_diagnose_sportarr_matches_by_series_id():
    res = await diagnose({"sportarr": FakeSportarr()}, title="Example League")
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


class FakeJf:
    type = "jellyfin"

    def __init__(self, name="jellyfin", items=None, fail=False):
        self.name = name
        self._items = items if items is not None else []
        self._fail = fail
        self.searched = []

    async def search_items(self, term, limit):
        self.searched.append((term, limit))
        if self._fail:
            raise RuntimeError("jellyfin down")
        return self._items, len(self._items)


class IdArr(FakeArr):
    async def lookup_library(self, term, media):
        return [{"title": "Show", "id": 7, "tvdbId": 111, "tmdbId": 0, "imdbId": None}]


async def test_diagnose_marks_in_jellyfin_by_tvdb():
    jf = FakeJf(items=[{"Name": "Show", "ProviderIds": {"Tvdb": "111"}}])
    res = await diagnose({"sonarr": IdArr(), "jellyfin": jf}, title="Show")
    assert res["matches"][0]["in_jellyfin"] is True
    assert jf.searched == [("Show", 50)]


async def test_diagnose_marks_in_jellyfin_by_tmdb_and_imdb():
    class MovieArr(FakeArr):
        name = "radarr"; type = "radarr"
        async def lookup_library(self, term, media):
            return [{"title": "Film", "id": 3, "tmdbId": 555, "imdbId": "tt9"}]
    by_tmdb = FakeJf(items=[{"Name": "Film", "ProviderIds": {"Tmdb": "555"}}])
    by_imdb = FakeJf(items=[{"Name": "Film", "ProviderIds": {"Imdb": "tt9"}}])
    for jf in (by_tmdb, by_imdb):
        res = await diagnose({"radarr": MovieArr(), "jellyfin": jf}, title="Film")
        assert res["matches"][0]["in_jellyfin"] is True


async def test_diagnose_no_id_match_is_false():
    jf = FakeJf(items=[{"Name": "Show", "ProviderIds": {"Tvdb": "999"}}])
    res = await diagnose({"sonarr": IdArr(), "jellyfin": jf}, title="Show")
    assert res["matches"][0]["in_jellyfin"] is False


async def test_diagnose_ignores_zero_ids():
    jf = FakeJf(items=[{"Name": "Show", "ProviderIds": {"Tmdb": "0"}}])
    res = await diagnose({"sonarr": IdArr(), "jellyfin": jf}, title="Show")
    assert res["matches"][0]["in_jellyfin"] is False


async def test_diagnose_matches_provider_ids_case_insensitively():
    jf = FakeJf(items=[{"Name": "Show", "ProviderIds": {"tvdb": "111"}}])
    res = await diagnose({"sonarr": IdArr(), "jellyfin": jf}, title="Show")
    assert res["matches"][0]["in_jellyfin"] is True


async def test_diagnose_jellyfin_down_gives_null_and_error():
    res = await diagnose({"sonarr": IdArr(), "jellyfin": FakeJf(fail=True)}, title="Show")
    assert res["matches"][0]["in_jellyfin"] is None
    assert res["errors"][0]["instance"] == "jellyfin"
    assert res["matches"][0]["in_library"] is True


async def test_diagnose_one_jellyfin_down_uses_the_other():
    up = FakeJf(name="jf-up", items=[{"Name": "Show", "ProviderIds": {"Tvdb": "111"}}])
    down = FakeJf(name="jf-down", fail=True)
    res = await diagnose({"sonarr": IdArr(), "jf-up": up, "jf-down": down}, title="Show")
    assert res["matches"][0]["in_jellyfin"] is True
    assert [e["instance"] for e in res["errors"]] == ["jf-down"]


async def test_diagnose_without_jellyfin_has_no_key():
    res = await diagnose({"sonarr": IdArr()}, title="Show")
    assert "in_jellyfin" not in res["matches"][0]
