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


def _iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat() + "T00:00:00Z"


class FakeRadarr:
    """Radarr movies carry several release dates and no airDate.

    Only physicalRelease falls inside a 7-day window here, so that is the date
    that put the movie in the calendar. digitalRelease is months in the past.
    """
    name = "radarr"; type = "radarr"
    async def calendar(self, start, end):
        return [{"title": "Invented Heist",
                 "inCinemas": _iso(-120),
                 "digitalRelease": _iso(-90),
                 "physicalRelease": _iso(2),
                 "releaseDate": _iso(-90),
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


async def test_when_reports_the_release_date_that_falls_inside_the_window():
    res = await get_upcoming({"radarr": FakeRadarr()})
    item = res[0]["data"][0]
    assert item["title"] == "Invented Heist"
    assert item["parent"] is None
    assert item["when"] == _iso(2)  # physicalRelease, not the past digitalRelease


async def test_when_falls_back_to_field_order_when_no_date_is_in_the_window():
    class AllPast:
        name = "radarr"; type = "radarr"
        async def calendar(self, start, end):
            return [{"title": "Old", "digitalRelease": _iso(-30),
                     "inCinemas": _iso(-60), "monitored": True, "hasFile": True}]

    res = await get_upcoming({"radarr": AllPast()})
    assert res[0]["data"][0]["when"] == _iso(-30)  # digitalRelease outranks inCinemas


async def test_when_is_none_when_the_record_carries_no_date():
    class NoDates:
        name = "sonarr"; type = "sonarr"
        async def calendar(self, start, end):
            return [{"title": "Undated", "monitored": True, "hasFile": False}]

    res = await get_upcoming({"sonarr": NoDates()})
    assert res[0]["data"][0]["when"] is None


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


class ManySportarr(FakeSportarr):
    async def calendar(self, start, end):
        rec = (await super().calendar(start, end))[0]
        return [rec] * 5


async def test_get_upcoming_bounds_per_instance():
    row = (await get_upcoming({"sportarr": ManySportarr()}, limit=2))[0]
    assert len(row["data"]) == 2
    assert row["total"] == 5 and row["truncated"] is True
