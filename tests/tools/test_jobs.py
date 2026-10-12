import json
from pathlib import Path

from oraclarr_mcp.tools.jobs import MAX_LIMIT, NOTE, duration_s, get_jobs

FX = Path(__file__).parent.parent / "fixtures"
SONARR_CMDS = json.loads((FX / "arr_commands_sonarr.json").read_text(encoding="utf-8"))
RADARR_CMDS = json.loads((FX / "arr_commands_radarr.json").read_text(encoding="utf-8"))
SONARR_TASKS = json.loads((FX / "arr_system_task_sonarr.json").read_text(encoding="utf-8"))
SECRET = "0123456789abcdef0123456789abcdef"


def _cmd(id, name, status, body=None, message=None, ended=None,
         queued="2026-10-13T01:00:00Z"):
    c = {"id": id, "name": name, "commandName": name, "status": status,
         "result": "unknown" if status in ("queued", "started") else "successful",
         "trigger": "manual", "queued": queued, "started": queued, "ended": ended,
         "duration": "00:01:02.5000000", "body": body or {"name": name}}
    if message is not None:
        c["message"] = message
    return c


RENAME = _cmd(9001, "RenameSeries", "started", {"seriesIds": list(range(1, 40))},
              message="Renaming files for series 7 of 39")
SEARCH = _cmd(9002, "SeriesSearch", "started", {"seriesId": 2})
FAILED = _cmd(9003, "RefreshSeries", "failed", {"seriesId": 3},
              ended="2026-10-13T01:05:00Z")
TITLES = {("series", i): f"Invented Show {i}" for i in range(1, 40)}
TITLES.update({("movie", m): f"Invented Film {m}"
               for c in RADARR_CMDS for m in c["body"].get("movieIds", [])})


class FakeArr:
    def __init__(self, name="sonarr", type="sonarr", commands=(), tasks=()):
        self.name, self.type = name, type
        self.cmds, self.tasks = list(commands), list(tasks)
        self.title_calls = []

    async def commands(self):
        return self.cmds

    async def system_tasks(self):
        return self.tasks

    async def titles(self, kind, ids):
        self.title_calls.append((kind, list(ids)))
        return [TITLES[(kind, i)] for i in list(ids)[:5] if (kind, i) in TITLES]


class FakeSportarr:
    name = "sportarr"; type = "sportarr"

    async def commands(self):
        raise AssertionError("Sportarr has no command list; no request may be made")


class FakeJf:
    name = "jellyfin"; type = "jellyfin"

    async def scheduled_tasks(self):
        return [{"Name": "Scan Media Library", "State": "Running",
                 "CurrentProgressPercentage": 42.0, "LastExecutionResult": {}},
                {"Name": "Idle Task", "State": "Idle",
                 "LastExecutionResult": {"Status": "Completed"}},
                {"Name": "Chapter Images", "State": "Idle",
                 "LastExecutionResult": {"Status": "Failed", "ErrorMessage": "boom"}}]


def _data(out, name="sonarr"):
    return next(r for r in out if r["instance"] == name)["data"]


async def test_buckets_active_failed_recent_with_routine_hidden():
    fake = FakeArr(commands=SONARR_CMDS + [RENAME, SEARCH, FAILED])
    d = _data(await get_jobs({"sonarr": fake}))
    assert [c["name"] for c in d["active"]] == ["RenameSeries", "SeriesSearch"]
    assert [c["name"] for c in d["failed"]] == ["RefreshSeries"]
    # The live sonarr fixture's only non-routine command is ImportListSync.
    assert [c["name"] for c in d["recent"]] == ["Import List Sync"]
    assert d["note"] == NOTE
    assert d["counts"] == {"active": 2, "failed": 1, "recent": len(d["recent"])}


async def test_include_routine_shows_routine_commands():
    fake = FakeArr(commands=SONARR_CMDS)
    d = _data(await get_jobs({"sonarr": fake}, include_routine=True))
    assert any(c["name"] == "Refresh Monitored Downloads" for c in d["recent"])


async def test_recent_is_newest_first_and_bounded():
    cmds = [_cmd(i, "ImportListSync", "completed", ended=f"2026-10-13T01:{i:02d}:00Z")
            for i in range(10)]
    out = await get_jobs({"sonarr": FakeArr(commands=cmds)}, limit=3)
    d = _data(out)
    assert [c["id"] for c in d["recent"]] == [9, 8, 7]
    assert d["counts"]["recent"] == 10 and out[0]["truncated"] is True


async def test_active_is_bounded_with_counts():
    cmds = [_cmd(i, "EpisodeSearch", "queued", {"episodeIds": [i]}) for i in range(300)]
    cmds += [FAILED, _cmd(9100, "ImportListSync", "completed", ended="2026-10-13T02:00:00Z")]
    out = await get_jobs({"sonarr": FakeArr(commands=cmds)}, limit=10**6)
    d = _data(out)
    assert len(d["active"]) == MAX_LIMIT and d["failed"] == [] and d["recent"] == []
    assert d["counts"] == {"active": 300, "failed": 1, "recent": 1}
    assert out[0]["truncated"] is True and out[0]["total"] == 302


async def test_limit_fills_active_then_failed_then_recent():
    cmds = [RENAME, SEARCH, FAILED] + [
        _cmd(100 + i, "ImportListSync", "completed", ended=f"2026-10-13T03:{i:02d}:00Z")
        for i in range(5)]
    d = _data(await get_jobs({"sonarr": FakeArr(commands=cmds)}, limit=4))
    assert (len(d["active"]), len(d["failed"]), len(d["recent"])) == (2, 1, 1)


async def test_unknown_status_goes_to_recent():
    d = _data(await get_jobs({"sonarr": FakeArr(commands=[_cmd(1, "X", "weird")])}))
    assert [c["status"] for c in d["recent"]] == ["weird"]


async def test_command_projection_and_series_titles():
    fake = FakeArr(commands=[RENAME])
    c = _data(await get_jobs({"sonarr": fake}))["active"][0]
    assert c == {"id": 9001, "name": "RenameSeries", "status": "started", "result": "unknown",
                 "trigger": "manual", "queued": "2026-10-13T01:00:00Z",
                 "started": "2026-10-13T01:00:00Z", "ended": None, "duration_s": 62.5,
                 "message": "Renaming files for series 7 of 39",
                 "items": {"kind": "series", "count": 39,
                           "titles": [f"Invented Show {i}" for i in range(1, 6)]}}


async def test_items_for_movies_episodes_files_and_unknown_bodies():
    movie = next(c for c in RADARR_CMDS if c["body"].get("movieIds"))
    cmds = [movie,
            _cmd(2, "EpisodeSearch", "started", {"episodeIds": [11, 12, 13], "seriesId": 4}),
            _cmd(3, "EpisodeSearch", "started", {"episodeIds": [14]}),
            _cmd(4, "RenameFiles", "started", {"seriesId": 5, "files": [1, 2]}),
            _cmd(5, "RssSync", "started", {"name": "RssSync", "isLongRunning": False})]
    d = _data(await get_jobs({"radarr": FakeArr("radarr", "radarr", cmds)}), "radarr")
    by_id = {c["id"]: c["items"] for c in d["active"] + d["recent"]}
    assert by_id[movie["id"]]["kind"] == "movie"
    assert by_id[movie["id"]]["count"] == len(movie["body"]["movieIds"])
    assert by_id[2] == {"kind": "episode", "count": 3, "titles": ["Invented Show 4"]}
    assert by_id[3] == {"kind": "episode", "count": 1, "titles": []}
    assert by_id[4] == {"kind": "file", "count": 2, "titles": ["Invented Show 5"]}
    assert by_id[5] is None


def test_duration_parsing():
    assert duration_s("00:00:00.0962323") == 0.096
    assert duration_s("1.02:03:04.5") == 93784.5
    assert duration_s("garbage") is None and duration_s(None) is None


async def test_message_redacted_before_cut():
    from oraclarr_mcp.call_guard import guarded
    from oraclarr_mcp.redact import Redactor
    cmd = _cmd(1, "RenameSeries", "started", message="x" * 290 + " " + SECRET)
    w = guarded("get_jobs", get_jobs, budget_s=5, max_bytes=200_000,
                redactor=Redactor([SECRET]))
    out = await w(clients={"sonarr": FakeArr(commands=[cmd])})
    assert SECRET[:8] not in json.dumps(out)


async def test_sportarr_gets_note_without_a_request():
    out = await get_jobs({"sportarr": FakeSportarr()})
    assert out[0]["status"] == "ok" and "not_supported" in out[0]["data"]


async def test_jellyfin_reports_running_and_failed_tasks():
    d = _data(await get_jobs({"jellyfin": FakeJf()}), "jellyfin")
    assert [t["name"] for t in d["tasks"]] == ["Scan Media Library", "Chapter Images"]
    assert d["tasks"][0]["progress"] == 42.0


async def test_service_filter_and_invalid_section():
    clients = {"sonarr": FakeArr(), "radarr": FakeArr("radarr", "radarr"), "jellyfin": FakeJf()}
    out = await get_jobs(clients, service="radarr")
    assert [r["instance"] for r in out] == ["radarr"]
    assert (await get_jobs(clients, section="bogus"))["error"] == "invalid_section"


async def test_other_types_are_ignored():
    class Netdata:
        name = "netdata"; type = "netdata"
    out = await get_jobs({"netdata": Netdata(), "sonarr": FakeArr()})
    assert [r["instance"] for r in out] == ["sonarr"]


async def test_schedule_rows_sorted_by_next_run():
    out = await get_jobs({"sonarr": FakeArr(tasks=SONARR_TASKS)}, section="schedule")
    rows = out[0]["data"]
    assert set(rows[0]) == {"name", "interval_min", "last_run", "next_run", "last_duration_s"}
    nxt = [r["next_run"] for r in rows]
    assert nxt == sorted(nxt) and len(rows) == len(SONARR_TASKS)
    assert all(isinstance(r["last_duration_s"], float) for r in rows if r["last_run"])


async def test_schedule_is_bounded_and_skips_jellyfin():
    clients = {"sonarr": FakeArr(tasks=SONARR_TASKS), "jellyfin": FakeJf(),
               "sportarr": FakeSportarr()}
    out = await get_jobs(clients, section="schedule", limit=3)
    assert [r["instance"] for r in out] == ["sonarr", "sportarr"]
    son = out[0]
    assert len(son["data"]) == 3 and son["truncated"] is True
    assert "not_supported" in out[1]["data"]
