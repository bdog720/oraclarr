from datetime import date, timedelta
from oraclarr_mcp.tools.upcoming import get_upcoming


class FakeSportarr:
    name = "sportarr"; type = "sportarr"
    def __init__(self): self.window = None
    async def calendar(self, start, end):
        self.window = (start, end)
        return [{"title": "Home Team vs Away Team",
                 "airDateUtc": "2026-10-09T00:00:00.0000000Z",
                 "monitored": True, "hasFile": False,
                 "series": {"title": "Example League"}}]


class FakeRadarr:
    name = "radarr"; type = "radarr"
    async def calendar(self, start, end):
        return [{"title": "Some Movie", "inCinemas": "2026-09-05T00:00:00Z",
                 "digitalRelease": "2026-09-12T00:00:00Z",
                 "monitored": True, "hasFile": False}]


class DeadArr:
    name = "dead"; type = "sonarr"
    async def calendar(self, start, end):
        raise RuntimeError("boom")


async def test_normalises_episode_records():
    res = await get_upcoming({"sportarr": FakeSportarr()})
    item = res[0]["data"][0]
    assert item["title"] == "Home Team vs Away Team"
    assert item["parent"] == "Example League"
    assert item["when"] == "2026-10-09T00:00:00.0000000Z"
    assert item["monitored"] is True
    assert item["has_file"] is False


async def test_radarr_movie_records_fall_back_to_release_dates():
    res = await get_upcoming({"radarr": FakeRadarr()})
    item = res[0]["data"][0]
    assert item["title"] == "Some Movie"
    assert item["parent"] is None
    assert item["when"] == "2026-09-12T00:00:00Z"  # digitalRelease wins over inCinemas


async def test_window_starts_today_and_spans_requested_days():
    arr = FakeSportarr()
    await get_upcoming({"sportarr": arr}, days=3)
    start, end = arr.window
    assert start == date.today().isoformat()
    assert end == (date.today() + timedelta(days=3)).isoformat()


async def test_days_is_clamped_to_one_and_ninety():
    arr = FakeSportarr()
    await get_upcoming({"sportarr": arr}, days=9999)
    assert arr.window[1] == (date.today() + timedelta(days=90)).isoformat()
    await get_upcoming({"sportarr": arr}, days=0)
    assert arr.window[1] == (date.today() + timedelta(days=1)).isoformat()


async def test_dead_instance_returns_envelope_and_peers_still_return_data():
    res = await get_upcoming({"sportarr": FakeSportarr(), "dead": DeadArr()})
    by_name = {r["instance"]: r for r in res}
    assert by_name["dead"]["status"] == "error"
    assert by_name["sportarr"]["status"] == "ok"


async def test_service_filter_selects_one_instance():
    res = await get_upcoming({"sportarr": FakeSportarr(), "radarr": FakeRadarr()},
                             service="radarr")
    assert len(res) == 1
    assert res[0]["instance"] == "radarr"
