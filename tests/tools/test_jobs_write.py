import asyncio
import logging

import httpx
import pytest

from oraclarr_mcp.plans import PLAN_TTL_S, PlanStore
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
        await asyncio.sleep(0)  # yield, so concurrent callers interleave like real I/O
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


async def _planned(clients, store, w, **kw):
    out = await start_job(clients, store, w, **kw)
    return out["plan_id"]


async def test_execute_sends_the_stored_request_once(caplog):
    clients, store, w = _env()
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await start_job(clients, store, w, action="ignored", plan_id=pid,
                              service="radarr", target="whatever")
    assert out == {"executed": True, "command_id": 777, "status": "queued",
                   "next": 'get_jobs(service="sonarr")'}
    assert clients["sonarr"].posts == [
        ("/api/v3/command", {"name": "RefreshSeries", "seriesId": 1}, None)]
    assert clients["radarr"].posts == []
    assert "event=executed" in caplog.text and "command_id=777" in caplog.text
    again = await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert again == {"error": "plan_not_found"}
    assert len(clients["sonarr"].posts) == 1


async def test_jellyfin_execute_has_no_command_id():
    clients, store, w = _env()
    pid = await _planned(clients, store, w, action="scan", service="jellyfin",
                         library="Shows")
    out = await start_job(clients, store, w, action="scan", plan_id=pid)
    assert out == {"executed": True, "next": 'get_jobs(service="jellyfin")'}
    assert clients["jellyfin"].posts == [("/Items/L1/Refresh", None, REFRESH_PARAMS)]


async def test_changed_rename_preview_is_plan_changed_with_a_fresh_plan():
    rows = [{"episodeFileId": 11, "existingPath": "o", "newPath": "n"}]
    sonarr = FakeArr(renames=rows)
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="rename", service="sonarr", target="id:1")
    sonarr.renames = rows + [{"episodeFileId": 12, "existingPath": "o2", "newPath": "n2"}]
    out = await start_job(clients, store, w, action="rename", plan_id=pid)
    assert out["error"] == "plan_changed" and out["plan_id"] != pid
    assert out["plan"]["request"]["json"]["files"] == [11, 12]
    assert sonarr.posts == []


async def test_target_gone_is_plan_changed_without_a_plan():
    sonarr = FakeArr()
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    del sonarr._items[1]
    out = await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert out["error"] == "plan_changed" and out["detail"]["error"] == "not_found"
    assert sonarr.posts == []


async def test_execute_rechecks_instance_opt_in():
    clients, store, w = _env()
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    out = await start_job(clients, store, {"radarr"}, action="refresh", plan_id=pid)
    assert out == {"error": "writes_not_allowed", "instance": "sonarr"}
    assert clients["sonarr"].posts == []


async def test_upstream_error_consumes_the_plan():
    sonarr = FakeArr()
    req = httpx.Request("POST", "http://h/api/v3/command")
    sonarr.post_error = httpx.HTTPStatusError(
        "bad", request=req,
        response=httpx.Response(400, json=[{"errorMessage": "Series is not monitored"}],
                                request=req))
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="search", service="sonarr", target="id:1")
    out = await start_job(clients, store, w, action="search", plan_id=pid)
    assert out == {"error": "upstream_error", "instance": "sonarr", "status": 400,
                   "message": "Series is not monitored"}
    assert (await start_job(clients, store, w, action="search", plan_id=pid))["error"]         == "plan_not_found"


async def test_send_timeout_is_unknown_and_not_retried(caplog):
    sonarr = FakeArr()
    sonarr.post_error = httpx.ReadTimeout("slow")
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert out == {"outcome": "unknown", "instance": "sonarr",
                   "next": 'get_jobs(service="sonarr")'}
    assert len(sonarr.posts) == 1 and "event=unknown" in caplog.text


async def test_undecodable_reply_is_unknown_not_an_escape(caplog):
    sonarr = FakeArr()
    sonarr.post_error = httpx.DecodingError("bad gzip")
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert out == {"outcome": "unknown", "instance": "sonarr",
                   "next": 'get_jobs(service="sonarr")'}
    assert len(sonarr.posts) == 1 and "event=unknown" in caplog.text


async def test_cancelled_send_is_audited_and_reraised(caplog):
    sonarr = FakeArr()
    sonarr.post_error = asyncio.CancelledError()
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        with pytest.raises(asyncio.CancelledError):
            await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert len(sonarr.posts) == 1
    assert "event=unknown" in caplog.text and "cancelled" in caplog.text


async def test_non_json_success_reply_counts_as_executed(caplog):
    sonarr = FakeArr()
    sonarr.post_error = ValueError("not json")
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert out == {"executed": True, "next": 'get_jobs(service="sonarr")'}
    assert len(sonarr.posts) == 1 and "event=executed" in caplog.text


async def test_connect_error_means_not_sent():
    sonarr = FakeArr()
    sonarr.post_error = httpx.ConnectError("refused")
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    out = await start_job(clients, store, w, action="refresh", plan_id=pid)
    assert out["error"] == "unreachable" and out["sent"] is False


async def test_expired_plan_is_not_found():
    class Clock:
        t = 0.0

        def __call__(self):
            return self.t
    clock = Clock()
    clients, _, w = _env()
    store = PlanStore(clock=clock)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    clock.t += PLAN_TTL_S
    assert (await start_job(clients, store, w, action="refresh", plan_id=pid)) ==         {"error": "plan_not_found"}


async def test_concurrent_execution_sends_once():
    clients, store, w = _env()
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    outs = await asyncio.gather(*(start_job(clients, store, w, action="refresh", plan_id=pid)
                                  for _ in range(5)))
    assert sum(o.get("executed") is True for o in outs) == 1
    assert len(clients["sonarr"].posts) == 1


async def test_plan_id_alone_executes_the_plan():
    clients, store, w = _env()
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")
    out = await start_job(clients, store, w, plan_id=pid)
    assert out["executed"] is True
    assert len(clients["sonarr"].posts) == 1


async def test_missing_action_without_plan_id_is_invalid_action():
    clients, store, w = _env()
    out = await start_job(clients, store, w, service="sonarr", target="id:1")
    assert out["error"] == "invalid_action"
    assert clients["sonarr"].posts == []


async def test_forged_plan_id_is_rejected_without_logging_it(caplog):
    clients, store, w = _env()
    forged = "x\naudit event=executed tool=start_job instance=sonarr"
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await start_job(clients, store, w, plan_id=forged)
    assert out == {"error": "plan_not_found"}
    assert clients["sonarr"].posts == []
    assert "event=refused" in caplog.text and "invalid_plan_id" in caplog.text
    assert "event=executed" not in caplog.text and "forged" not in caplog.text
    assert "x\n" not in caplog.text and "audit event=executed" not in caplog.text
    assert all("\n" not in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("bad", ["", "short", "a" * 17, "a" * 15 + "!", "a" * 15 + "\n"])
async def test_malformed_plan_id_never_reaches_the_store(bad):
    clients, store, w = _env()
    taken = []
    store.take = lambda pid: taken.append(pid)
    out = await start_job(clients, store, w, plan_id=bad)
    assert out == {"error": "plan_not_found"} and taken == []


async def test_rename_rows_without_file_ids_are_nothing_to_do():
    rows = [{"existingPath": "a", "newPath": "b"}]
    clients, store, w = _env(sonarr=FakeArr(renames=rows))
    out = await _plan(clients, store, w, action="rename", service="sonarr", target="id:1")
    assert out["nothing_to_do"] is True and "plan_id" not in out
    assert out["detail"] == "the rename preview has no file ids"
    assert out["target"]["id"] == 1
    assert store._plans == {}


async def test_execute_under_a_deadline_times_out_as_unknown_and_never_retries(caplog):
    from oraclarr_mcp.call_guard import guarded
    from oraclarr_mcp.redact import Redactor

    class SlowArr(FakeArr):
        async def post(self, path, json=None, params=None):
            self.posts.append((path, json, params))
            await asyncio.sleep(2)

    sonarr = SlowArr()
    clients, store, w = _env(sonarr=sonarr)
    pid = await _planned(clients, store, w, action="refresh", service="sonarr", target="id:1")

    async def run(**kw):
        return await start_job(clients, store, w, **kw)

    g = guarded("start_job", run, budget_s=0.3, max_bytes=200_000, redactor=Redactor([]))
    with caplog.at_level(logging.INFO, logger="oraclarr_mcp.audit"):
        out = await g(plan_id=pid)
        again = await g(plan_id=pid)
    assert out["outcome"] == "unknown"
    assert len(sonarr.posts) == 1 and "event=unknown" in caplog.text
    assert again == {"error": "plan_not_found"}
