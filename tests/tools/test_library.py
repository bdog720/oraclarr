from oraclarr_mcp.tools.library import get_library, search_row

FOLDERS = [
    {"Name": "Shows", "CollectionType": "tvshows", "ItemId": "a", "RefreshStatus": "Idle",
     "RefreshProgress": None, "Locations": ["/tv"], "LibraryOptions": {"big": "blob"}},
    {"Name": "Movies", "CollectionType": "movies", "ItemId": "b", "RefreshStatus": "Active",
     "RefreshProgress": 37.456, "Locations": ["/movies"]},
]
TASKS = [
    {"Name": "Scan Media Library", "State": "Running", "CurrentProgressPercentage": 12.5,
     "LastExecutionResult": {"Status": "Completed", "EndTimeUtc": "2026-10-11T00:00:00Z"}},
    {"Name": "Extract Chapter Images", "State": "Idle",
     "LastExecutionResult": {"Status": "Failed", "EndTimeUtc": "2026-10-10T00:00:00Z",
                             "ErrorMessage": "ffmpeg exited 1"}},
    {"Name": "Clean Cache", "State": "Idle",
     "LastExecutionResult": {"Status": "Completed", "EndTimeUtc": "2026-10-10T00:00:00Z"}},
]
PLAYING = {"UserName": "u1", "Client": "Jellyfin Web", "DeviceName": "TV",
           "NowPlayingItem": {"Name": "Pilot", "SeriesName": "The Rookie"},
           "PlayState": {"PlayMethod": "Transcode", "IsPaused": False},
           "TranscodingInfo": {"VideoCodec": "h264", "AudioCodec": "aac", "Container": "ts",
                               "HardwareAccelerationType": "nvenc",
                               "TranscodeReasons": ["VideoCodecNotSupported"],
                               "CompletionPercentage": 41.0, "Width": 1920}}
IDLE = {"UserName": "u2", "Client": "Android", "DeviceName": "Phone"}
RECENT = [{"Name": f"Ep {i}", "Type": "Episode", "SeriesName": "Show", "ParentIndexNumber": 1,
           "IndexNumber": i, "DateCreated": f"2026-10-{i:02d}T00:00:00Z", "ImageTags": {}}
          for i in range(1, 31)]
SEARCH = [{"Name": "The Rookie", "Type": "Series", "ProductionYear": 2018,
           "Path": "/tv/The Rookie (2018)", "DateCreated": "2026-01-01T00:00:00Z",
           "ProviderIds": {"Tvdb": "350665", "Tmdb": "79744", "Imdb": "tt7587890"},
           "ImageTags": {"Primary": "x"}}]


class FakeJf:
    name = "jellyfin"; type = "jellyfin"

    def __init__(self):
        self.calls = []

    async def system_info(self):
        self.calls.append("system_info")
        return {"Version": "12.2.0", "HasPendingRestart": False, "HasUpdateAvailable": True}

    async def virtual_folders(self):
        self.calls.append("virtual_folders")
        return FOLDERS

    async def library_count(self, parent_id):
        return {"a": 120, "b": 900}[parent_id]

    async def scheduled_tasks(self):
        self.calls.append("scheduled_tasks")
        return TASKS

    async def sessions(self):
        self.calls.append("sessions")
        return [PLAYING, IDLE]

    async def recent_items(self, limit):
        self.calls.append(("recent_items", limit))
        return RECENT[:limit], len(RECENT)

    async def search_items(self, term, limit):
        self.calls.append(("search_items", term, limit))
        return SEARCH, 1


async def test_summary_shape_and_filters():
    row = (await get_library({"jellyfin": FakeJf()}))[0]
    assert row["status"] == "ok"
    d = row["data"]
    assert d["version"] == "12.2.0" and d["pending_restart"] is False
    assert [lib["name"] for lib in d["libraries"]] == ["Shows", "Movies"]
    assert [t["name"] for t in d["tasks"]] == ["Scan Media Library", "Extract Chapter Images"]
    assert [s["user"] for s in d["sessions"]] == ["u1"]
    assert len(d["recent"]) == 10


async def test_library_row_reports_active_scan_progress():
    d = (await get_library({"jellyfin": FakeJf()}, section="libraries"))[0]["data"]
    assert d[0] == {"name": "Shows", "type": "tvshows", "items": 120, "scan": "Idle",
                    "scan_progress": None}
    assert d[1]["scan"] == "Active" and d[1]["scan_progress"] == 37.5


async def test_task_row_fields():
    d = (await get_library({"jellyfin": FakeJf()}, section="tasks"))[0]["data"]
    assert d[1] == {"name": "Extract Chapter Images", "state": "Idle", "progress": None,
                    "last_status": "Failed", "last_end": "2026-10-10T00:00:00Z",
                    "last_error": "ffmpeg exited 1"}
    assert len(d) == 3


async def test_session_row_with_transcode():
    d = (await get_library({"jellyfin": FakeJf()}, section="sessions"))[0]["data"]
    assert d[0] == {
        "user": "u1", "client": "Jellyfin Web", "device": "TV", "item": "Pilot",
        "series": "The Rookie", "play_method": "Transcode", "paused": False,
        "transcode": {"video_codec": "h264", "audio_codec": "aac", "container": "ts",
                      "hw": "nvenc", "reasons": ["VideoCodecNotSupported"], "progress": 41.0},
    }


async def test_idle_session_projects_without_crash():
    d = (await get_library({"jellyfin": FakeJf()}, section="sessions"))[0]["data"]
    assert d[1]["item"] is None and d[1]["transcode"] is None and d[1]["play_method"] is None


async def test_recent_section_bounds_and_projects():
    fake = FakeJf()
    row = (await get_library({"jellyfin": fake}, section="recent", limit=5))[0]
    assert len(row["data"]) == 5 and row["total"] == 30 and row["truncated"] is True
    assert row["data"][0] == {"name": "Ep 1", "type": "Episode", "series": "Show", "season": 1,
                              "episode": 1, "added": "2026-10-01T00:00:00Z"}
    assert ("recent_items", 5) in fake.calls


async def test_term_search_wins_over_section():
    fake = FakeJf()
    row = (await get_library({"jellyfin": fake}, section="tasks", term="Rookie"))[0]
    assert row["data"][0] == {"name": "The Rookie", "type": "Series", "year": 2018,
                              "path": "/tv/The Rookie (2018)", "tvdb_id": "350665",
                              "tmdb_id": "79744", "imdb_id": "tt7587890",
                              "added": "2026-01-01T00:00:00Z"}
    assert "scheduled_tasks" not in fake.calls


def test_search_item_lowercases_provider_keys():
    row = search_row({"Name": "X", "ProviderIds": {"tvdb": "1", "TMDB": "2"}})
    assert row["tvdb_id"] == "1" and row["tmdb_id"] == "2" and row["imdb_id"] is None
    assert search_row({"Name": "Y"})["tvdb_id"] is None


async def test_invalid_section_returns_error_without_upstream_calls():
    fake = FakeJf()
    out = await get_library({"jellyfin": fake}, section="users")
    assert out == {"error": "invalid_section",
                   "valid": ["libraries", "recent", "sessions", "tasks"]}
    assert fake.calls == []


async def test_limit_is_clamped():
    fake = FakeJf()
    await get_library({"jellyfin": fake}, section="recent", limit=0)
    await get_library({"jellyfin": fake}, section="recent", limit=10_000)
    assert ("recent_items", 1) in fake.calls and ("recent_items", 100) in fake.calls


async def test_only_jellyfin_instances_are_queried():
    class Arr:
        name = "sonarr"; type = "sonarr"
    out = await get_library({"sonarr": Arr(), "jellyfin": FakeJf()}, section="libraries")
    assert [r["instance"] for r in out] == ["jellyfin"]
