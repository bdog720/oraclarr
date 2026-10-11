from oraclarr_mcp.tools.history import get_history
from oraclarr_mcp.tools.wanted import get_wanted
from oraclarr_mcp.tools.search import search_media

HISTORY = {"date": "2026-10-11T10:00:00Z", "eventType": "grabbed", "sourceTitle": "X.S01E01",
           "series": {"title": "X"}, "quality": {"quality": {"name": "WEBDL-1080p"}},
           "customFormatScore": 50, "downloadId": "ABC", "data": {"huge": "blob"}}

MISSING = {"title": "Pilot", "seriesId": 1, "seasonNumber": 1, "episodeNumber": 1,
           "airDateUtc": "2026-10-01T00:00:00Z", "monitored": True,
           "series": {"title": "Show", "images": [{"url": "x"}]}}

CUTOFF_MOVIE = {"title": "Film", "monitored": True, "digitalRelease": "2026-09-01T00:00:00Z"}

SERIES = {"title": "Show", "year": 2020, "tvdbId": 1, "tmdbId": 2, "imdbId": "tt3",
          "monitored": True, "status": "continuing", "path": "/tv/Show",
          "images": [{"url": "x"}], "seasons": [{"seasonNumber": 1}],
          "statistics": {"sizeOnDisk": 999, "episodeFileCount": 8, "episodeCount": 10}}


class FakeArr:
    name = "sonarr"; type = "sonarr"

    def __init__(self):
        self.page_sizes = []

    async def history_page(self, limit):
        self.page_sizes.append(limit)
        return [HISTORY] * min(limit, 3), 3

    async def wanted_page(self, kind, limit):
        self.page_sizes.append(limit)
        if kind == "missing":
            return [MISSING] * min(limit, 2), 40
        return [CUTOFF_MOVIE] * min(limit, 2), 5

    async def lookup_library(self, term, media):
        return [dict(SERIES, title=f"{term} {i}") for i in range(30)]


async def test_get_history_projects_and_bounds():
    res = await get_history({"sonarr": FakeArr()}, service="sonarr", limit=2)
    row = res[0]
    assert row["status"] == "ok"
    assert row["data"][0] == {
        "date": "2026-10-11T10:00:00Z", "event_type": "grabbed", "source_title": "X.S01E01",
        "title": "X", "quality": "WEBDL-1080p", "custom_format_score": 50,
        "download_id": "ABC",
    }
    assert len(row["data"]) == 2
    assert row["total"] == 3 and row["truncated"] is True


async def test_get_history_unknown_service_returns_empty():
    assert await get_history({"sonarr": FakeArr()}, service="nope", limit=5) == []


async def test_get_history_clamps_limit():
    fake = FakeArr()
    await get_history({"sonarr": fake}, limit=0)
    await get_history({"sonarr": fake}, limit=10_000)
    assert fake.page_sizes == [1, 80]


async def test_get_wanted_merges_projects_and_bounds():
    res = await get_wanted({"sonarr": FakeArr()}, service="sonarr", limit=3)
    row = res[0]
    assert row["data"][0] == {
        "title": "Pilot", "parent": "Show", "season": 1, "episode": 1,
        "air_date": "2026-10-01T00:00:00Z", "monitored": True, "reason": "missing",
    }
    assert row["data"][2]["reason"] == "cutoff"
    assert row["data"][2]["air_date"] == "2026-09-01T00:00:00Z"
    assert len(row["data"]) == 3
    assert row["total"] == 45 and row["truncated"] is True


async def test_search_media_projects_and_bounds():
    res = await search_media({"sonarr": FakeArr()}, term="Foo", limit=5)
    row = res[0]
    assert len(row["data"]) == 5
    assert row["total"] == 30 and row["truncated"] is True
    assert row["data"][0] == {
        "title": "Foo 0", "year": 2020, "tvdb_id": 1, "tmdb_id": 2, "imdb_id": "tt3",
        "monitored": True, "status": "continuing", "path": "/tv/Show",
        "size_on_disk": 999, "episode_file_count": 8, "episode_count": 10, "has_file": None,
    }


async def test_search_media_movie_uses_top_level_size():
    class FakeRadarr:
        name = "radarr"; type = "radarr"
        async def lookup_library(self, term, media):
            assert media == "movie"
            return [{"title": "Film", "sizeOnDisk": 42, "hasFile": True}]
    row = (await search_media({"radarr": FakeRadarr()}, term="Film"))[0]
    assert row["data"][0]["size_on_disk"] == 42
    assert row["data"][0]["has_file"] is True
