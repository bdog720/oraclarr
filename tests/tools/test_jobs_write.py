import logging

import httpx

from oraclarr_mcp.plans import PlanStore
from oraclarr_mcp.tools.jobs_write import MAX_PREVIEW_ROWS, REFRESH_PARAMS, start_job

SERIES = [{"id": 1, "title": "Invented Show", "year": 2020, "path": "/tv/Invented Show",
           "monitored": True, "statistics": {"episodeCount": 10, "episodeFileCount": 8},
           "seasons": [{"seasonNumber": 1, "monitored": True,
                        "statistics": {"episodeCount": 10, "episodeFileCount": 8}}]},
          {"id": 2, "title": "Remade Show", "year": 1990, "path": "/tv/Remade Show (1990)"},
          {"id": 3, "title": "Remade Show", "year": 2021, "path": "/tv/Remade Show (2021)"},
          {"id": 4, "title": "Another Invented Show", "year": 2019, "path": "/tv/Another"}]
MOVIES = [{"id": 9, "title": "Invented Film", "year": 2001, "path": "/movies/Invented Film",
           "monitored": True, "hasFile": False}]


class FakeArr:
    def __init__(self, name="sonarr", type="sonarr", items=SERIES, renames=None):
        self.name, self.type = name, type
        self._items = {i["id"]: i for i in items}
        self.renames = renames if renames is not None else []
        self.posts = []
        self.post_result = {"id": 777, "name": "X", "status": "queued"}
        self.post_error = None

    async def items(self, kind):
        return list(self._items.values())

    async def item(self, kind, item_id):
        return self._items.get(item_id)

    async def rename_preview(self, kind, item_id):
        return self.renames

    async def post(self, path, json=None, params=None):
        self.posts.append((path, json, params))
        if self.post_error:
            raise self.post_error
        return self.post_result


class FakeJf:
    name = "jellyfin"; type = "jellyfin"

    def __init__(self, state="Idle"):
        self.state = state
        self.posts = []

    async def scheduled_tasks(self):
        return [{"Name": "Scan Media Library", "Key": "RefreshLibrary", "Id": "T1",
                 "State": self.state}]

    async def virtual_folders(self):
        return [{"Name": "Shows", "ItemId": "L1"}, {"Name": "Anime", "ItemId": "L2"}]

    async def post(self, path, json=None, params=None):
        self.posts.append((path, json, params))
        return None


def _env(**clients):
    clients = clients or {"sonarr": FakeArr(), "radarr": FakeArr("radarr", "radarr", MOVIES),
                          "jellyfin": FakeJf()}
    return clients, PlanStore(), set(clients)


async def _plan(clients, store, writable, **kw):
    return await start_job(clients, store, writable, **kw)


async def test_refresh_plan_has_exact_command_and_target():
    clients, store, w = _env()
    out = await _plan(clients, store, w, action="refresh", service="sonarr",
                      target="invented show")
    assert out["expires_in_s"] == 600 and out["plan_id"]
    p = out["plan"]
    assert p["request"] == {"method": "POST", "path": "/api/v3/command",
                            "json": {"name": "RefreshSeries", "seriesId": 1}, "params": None}
    assert p["target"] == {"title": "Invented Show", "year": 2020, "id": 1,
                           "path": "/tv/Invented Show", "kind": "series"}
    assert clients["sonarr"].posts == []


async def test_every_arr_body():
    cases = [("sonarr", "rescan", {}, {"name": "RescanSeries", "seriesId": 1}),
             ("sonarr", "search", {}, {"name": "SeriesSearch", "seriesId": 1}),
             ("sonarr", "search", {"season": 1},
              {"name": "SeasonSearch", "seriesId": 1, "seasonNumber": 1}),
             ("radarr", "refresh", {}, {"name": "RefreshMovie", "movieIds": [9]}),
             ("radarr", "rescan", {}, {"name": "RescanMovie", "movieId": 9}),
             ("radarr", "search", {}, {"name": "MoviesSearch", "movieIds": [9]})]
    for service, action, extra, body in cases:
        clients, store, w = _env()
        target = "id:1" if service == "sonarr" else "id:9"
        out = await _plan(clients, store, w, action=action, service=service, target=target,
                          **extra)
        assert out["plan"]["request"]["json"] == body, (service, action)


async def test_search_previews():
    clients, store, w = _env()
    s = (await _plan(clients, store, w, action="search", service="sonarr", target="id:1",
                     season=1))["plan"]["preview"]
    assert s == {"monitored": True, "episodes": 10, "with_files": 8, "missing": 2,
                 "season": 1}
    m = (await _plan(clients, store, w, action="search", service="radarr",
                     target="Invented Film"))["plan"]["preview"]
    assert m == {"monitored": True, "has_file": False}


async def test_unknown_season_is_not_found():
    clients, store, w = _env()
    out = await _plan(clients, store, w, action="search", service="sonarr", target="id:1",
                      season=7)
    assert out["error"] == "not_found" and out["season"] == 7


async def test_rename_plan_uses_preview_files():
    rows = [{"seriesId": 1, "episodeFileId": 11, "existingPath": "a/old1.mkv",
             "newPath": "a/new1.mkv"},
            {"seriesId": 1, "episodeFileId": 12, "existingPath": "a/old2.mkv",
             "newPath": "a/new2.mkv"}]
    clients, store, w = _env(sonarr=FakeArr(renames=rows))
    out = await _plan(clients, store, w, action="rename", service="sonarr", target="id:1")
    assert out["plan"]["request"]["json"] == {"name": "RenameFiles", "seriesId": 1,
                                              "files": [11, 12]}
    assert out["plan"]["preview"] == {"count": 2, "rows": [
        {"existing": "a/old1.mkv", "new": "a/new1.mkv"},
        {"existing": "a/old2.mkv", "new": "a/new2.mkv"}]}


async def test_rename_preview_is_capped():
    rows = [{"episodeFileId": i, "existingPath": f"o{i}", "newPath": f"n{i}"}
            for i in range(80)]
    clients, store, w = _env(sonarr=FakeArr(renames=rows))
    out = await _plan(clients, store, w, action="rename", service="sonarr", target="id:1")
    assert out["plan"]["preview"]["count"] == 80
    assert len(out["plan"]["preview"]["rows"]) == MAX_PREVIEW_ROWS
    assert len(out["plan"]["request"]["json"]["files"]) == 80


async def test_rename_preview_tolerates_missing_keys():
    rows = [{"movieFileId": 5}, {"existingPath": "x"}]
    clients, store, w = _env(radarr=FakeArr("radarr", "radarr", MOVIES, renames=rows))
    out = await _plan(clients, store, w, action="rename", service="radarr", target="id:9")
    assert out["plan"]["request"]["json"] == {"name": "RenameFiles", "movieId": 9,
                                              "files": [5]}
    assert out["plan"]["preview"]["rows"][0] == {"existing": None, "new": None}


async def test_empty_rename_preview_is_nothing_to_do_and_stores_no_plan():
    clients, store, w = _env()
    out = await _plan(clients, store, w, action="rename", service="sonarr", target="id:1")
    assert out["nothing_to_do"] is True and "plan_id" not in out
    assert store._plans == {}


async def test_target_resolution():
    clients, store, w = _env()
    assert (await _plan(clients, store, w, action="refresh", service="sonarr",
                        target="nope"))["error"] == "not_found"
    assert (await _plan(clients, store, w, action="refresh", service="sonarr",
                        target="id:99"))["error"] == "not_found"
    assert (await _plan(clients, store, w, action="refresh", service="sonarr",
                        target="id:x"))["error"] == "not_found"
    sub = await _plan(clients, store, w, action="refresh", service="sonarr",
                      target="another")
    assert sub["plan"]["target"]["id"] == 4


async def test_exact_title_twice_is_ambiguous():
    clients, store, w = _env()
    out = await _plan(clients, store, w, action="refresh", service="sonarr",
                      target="Remade Show")
    assert out["error"] == "ambiguous"
    assert [c["year"] for c in out["candidates"]] == [1990, 2021]


async def test_substring_matching_many_is_ambiguous():
    clients, store, w = _env()
    out = await _plan(clients, store, w, action="refresh", service="sonarr", target="show")
    assert out["error"] == "ambiguous" and len(out["candidates"]) == 4


async def test_jellyfin_scan_all_and_one_library():
    clients, store, w = _env()
    a = (await _plan(clients, store, w, action="scan", service="jellyfin"))["plan"]
    assert a["request"] == {"method": "POST", "path": "/ScheduledTasks/Running/T1",
                            "json": None, "params": None}
    assert a["preview"] == {"libraries": ["Shows", "Anime"], "scanning": False}
    one = (await _plan(clients, store, w, action="scan", service="jellyfin",
                       library="anime"))["plan"]
    assert one["request"]["path"] == "/Items/L2/Refresh"
    assert one["request"]["params"] == REFRESH_PARAMS
    assert one["preview"]["libraries"] == ["Anime"]
    bad = await _plan(clients, store, w, action="scan", service="jellyfin", library="Music")
    assert bad["error"] == "not_found" and bad["valid"] == ["Shows", "Anime"]


async def test_scan_notes_a_running_scan():
    clients, store, w = _env(jellyfin=FakeJf(state="Running"))
    out = await _plan(clients, store, w, action="scan", service="jellyfin")
    assert out["plan"]["preview"]["scanning"] is True


async def test_validation_errors():
    class Sportarr(FakeArr):
        pass
    clients, store, w = _env(sonarr=FakeArr(), sportarr=Sportarr("sportarr", "sportarr"),
                             jellyfin=FakeJf())
    assert (await _plan(clients, store, w, action="delete", service="sonarr"))["error"] \
        == "invalid_action"
    assert (await _plan(clients, store, w, action="refresh", service="nope"))["error"] \
        == "invalid_service"
    assert (await _plan(clients, store, w, action="refresh", service="sportarr",
                        target="x"))["error"] == "not_supported"
    assert (await _plan(clients, store, w, action="scan", service="sonarr"))["error"] \
        == "invalid_service"
    assert (await _plan(clients, store, w, action="refresh", service="jellyfin"))["error"] \
        == "invalid_service"
    assert (await _plan(clients, store, w, action="refresh", service="sonarr"))["error"] \
        == "target_required"
    assert (await _plan(clients, store, w, action="refresh", service="sonarr", target="id:1",
                        season=1))["error"] == "invalid_argument"


async def test_not_opted_in_instance_is_refused_and_audited(caplog):
    clients, store, _ = _env()
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await _plan(clients, store, {"radarr"}, action="refresh", service="sonarr",
                          target="id:1")
    assert out == {"error": "writes_not_allowed", "instance": "sonarr"}
    assert "event=refused" in caplog.text


async def test_planned_event_is_audited(caplog):
    clients, store, w = _env()
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await _plan(clients, store, w, action="refresh", service="sonarr",
                          target="id:1")
    assert "event=planned" in caplog.text and out["plan_id"] in caplog.text


async def test_upstream_failure_while_planning_is_a_status():
    class Down(FakeArr):
        async def item(self, kind, item_id):
            raise httpx.ConnectError("down")
    clients, store, w = _env(sonarr=Down())
    out = await _plan(clients, store, w, action="refresh", service="sonarr", target="id:1")
    assert out["error"] == "unreachable" and out["instance"] == "sonarr"
