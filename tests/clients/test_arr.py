import asyncio
import json
import httpx
import respx
from pathlib import Path
from oraclarr_mcp.clients import arr as arr_mod
from oraclarr_mcp.clients.arr import ArrClient
from oraclarr_mcp.clients.base import ApiKeyHeaderAuth

FX = Path(__file__).parent.parent / "fixtures"

def _client():
    return ArrClient("sonarr", "sonarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5)

@respx.mock
async def test_system_status():
    respx.get("http://h/api/v3/system/status").mock(
        return_value=httpx.Response(200, json=json.loads((FX/"sonarr_status.json").read_text())))
    c = _client()
    assert (await c.system_status())["version"] == "4.0.10"
    await c.aclose()

@respx.mock
async def test_queue_returns_records():
    respx.get("http://h/api/v3/queue").mock(
        return_value=httpx.Response(200, json=json.loads((FX/"sonarr_queue.json").read_text())))
    c = _client()
    recs = await c.queue()
    assert recs[0]["downloadId"] == "ABC123"
    await c.aclose()

@respx.mock
async def test_item_history_series_path_and_param():
    payload = json.loads((FX/"sonarr_history_series.json").read_text())
    route = respx.get("http://h/api/v3/history/series").mock(
        return_value=httpx.Response(200, json=payload))
    c = _client()
    recs = await c.item_history(237, "series")
    assert route.calls.last.request.url.params["seriesId"] == "237"
    assert recs[0]["customFormatScore"] == 926880
    await c.aclose()

@respx.mock
async def test_item_history_movie_uses_movie_param():
    route = respx.get("http://h/api/v3/history/movie").mock(
        return_value=httpx.Response(200, json=[]))
    c = ArrClient("radarr", "radarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5)
    await c.item_history(42, "movie")
    assert route.calls.last.request.url.params["movieId"] == "42"
    await c.aclose()

@respx.mock
async def test_calendar_sends_window_and_includes_series():
    payload = json.loads((FX/"sportarr_calendar.json").read_text())
    route = respx.get("http://h/api/v3/calendar").mock(
        return_value=httpx.Response(200, json=payload))
    c = ArrClient("sportarr", "sportarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5)
    recs = await c.calendar("2026-10-09", "2026-10-11")
    params = route.calls.last.request.url.params
    assert params["start"] == "2026-10-09"
    assert params["end"] == "2026-10-11"
    assert params["includeSeries"] == "true"
    assert recs[0]["series"]["title"] == "Example League"
    await c.aclose()


@respx.mock
async def test_history_page_returns_records_and_total():
    route = respx.get("http://h/api/v3/history").mock(return_value=httpx.Response(
        200, json={"records": [{"eventType": "grabbed"}], "totalRecords": 812}))
    c = _client()
    records, total = await c.history_page(5)
    params = route.calls.last.request.url.params
    assert params["pageSize"] == "5"
    assert params["sortKey"] == "date"
    assert params["sortDirection"] == "descending"
    assert params["includeSeries"] == "true"
    assert params["includeMovie"] == "true"
    assert records == [{"eventType": "grabbed"}] and total == 812
    await c.aclose()


@respx.mock
async def test_wanted_page_uses_kind_path_and_page_size():
    route = respx.get("http://h/api/v3/wanted/cutoff").mock(return_value=httpx.Response(
        200, json={"records": [{"title": "Ep"}], "totalRecords": 3}))
    c = _client()
    records, total = await c.wanted_page("cutoff", 50)
    params = route.calls.last.request.url.params
    assert params["pageSize"] == "50"
    assert params["includeSeries"] == "true"
    assert records == [{"title": "Ep"}] and total == 3
    await c.aclose()


@respx.mock
async def test_queue_page_returns_records_and_total():
    route = respx.get("http://h/api/v3/queue").mock(return_value=httpx.Response(
        200, json={"records": [{"title": "A"}], "totalRecords": 300}))
    c = _client()
    records, total = await c.queue_page(100)
    assert route.calls.last.request.url.params["pageSize"] == "100"
    assert records == [{"title": "A"}] and total == 300
    await c.aclose()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _jclient(clock=None):
    return ArrClient("sonarr", "sonarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5,
                     clock=clock or Clock())


def _jfx(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))


@respx.mock
async def test_commands_and_system_tasks_read_their_endpoints():
    respx.get("http://h/api/v3/command").mock(
        return_value=httpx.Response(200, json=_jfx("arr_commands_sonarr")))
    respx.get("http://h/api/v3/system/task").mock(
        return_value=httpx.Response(200, json=_jfx("arr_system_task_sonarr")))
    c = _jclient()
    assert len(await c.commands()) == len(_jfx("arr_commands_sonarr"))
    assert (await c.system_tasks())[0]["taskName"]
    assert {call.request.method for call in respx.calls} == {"GET"}


@respx.mock
async def test_titles_first_five_in_order_and_cached():
    clock = Clock()
    routes = {i: respx.get(f"http://h/api/v3/series/{i}").mock(
        return_value=httpx.Response(200, json={"id": i, "title": f"Show {i}"}))
        for i in range(1, 8)}
    c = _jclient(clock)
    assert await c.titles("series", [3, 1, 2, 4, 5, 6, 7]) == [
        "Show 3", "Show 1", "Show 2", "Show 4", "Show 5"]
    assert routes[6].call_count == 0 and routes[7].call_count == 0
    await c.titles("series", [3, 1])
    assert routes[3].call_count == 1
    clock.t += arr_mod.TITLE_TTL_S
    await c.titles("series", [3])
    assert routes[3].call_count == 2


@respx.mock
async def test_titles_skip_missing_and_failed_ids():
    respx.get("http://h/api/v3/movie/1").mock(return_value=httpx.Response(404, json={}))
    respx.get("http://h/api/v3/movie/2").mock(side_effect=httpx.ConnectError("down"))
    respx.get("http://h/api/v3/movie/3").mock(
        return_value=httpx.Response(200, json={"id": 3, "title": "Film 3"}))
    assert await _jclient().titles("movie", [1, 2, 3]) == ["Film 3"]


async def test_titles_return_what_arrived_within_budget(monkeypatch):
    monkeypatch.setattr(arr_mod, "TITLE_BUDGET_S", 0.05)
    c = _jclient()

    async def fake_get_json(path, params=None):
        if path.endswith("/1"):
            await asyncio.sleep(5)  # a stuck lookup
        return {"title": "Show 2"}

    c.get_json = fake_get_json
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    assert await c.titles("series", [1, 2]) == ["Show 2"]
    assert loop.time() - t0 < 1.0


async def test_titles_empty_ids_makes_no_request():
    assert await _jclient().titles("series", []) == []


@respx.mock
async def test_titles_drop_non_object_replies():
    respx.get("http://h/api/v3/series/1").mock(return_value=httpx.Response(200, json=None))
    respx.get("http://h/api/v3/series/2").mock(return_value=httpx.Response(200, json=["x"]))
    respx.get("http://h/api/v3/series/3").mock(
        return_value=httpx.Response(200, json={"id": 3, "title": "Show 3"}))
    assert await _jclient().titles("series", [1, 2, 3]) == ["Show 3"]


async def test_titles_respect_the_tool_deadline():
    from oraclarr_mcp.budget import reset_deadline, set_deadline
    c = _jclient()

    async def stuck(path, params=None):
        await asyncio.sleep(5)

    c.get_json = stuck
    token = set_deadline(0.6)  # less than TITLE_BUDGET_S (5 s) is left
    try:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        assert await c.titles("series", [1, 2]) == []
        assert loop.time() - t0 < 0.5
    finally:
        reset_deadline(token)


async def test_cancelled_titles_call_cancels_its_lookups():
    c = _jclient()
    cancelled = []

    async def stuck(path, params=None):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(path)
            raise

    c.get_json = stuck
    outer = asyncio.ensure_future(c.titles("series", [1, 2]))
    await asyncio.sleep(0.05)
    outer.cancel()
    for _ in range(5):
        await asyncio.sleep(0)
    assert sorted(cancelled) == ["/api/v3/series/1", "/api/v3/series/2"]


@respx.mock
async def test_items_item_and_rename_preview():
    respx.get("http://h/api/v3/series").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "A"}]))
    respx.get("http://h/api/v3/series/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "title": "A"}))
    respx.get("http://h/api/v3/series/2").mock(return_value=httpx.Response(404, json={}))
    route = respx.get("http://h/api/v3/rename").mock(return_value=httpx.Response(200, json=[]))
    c = _client()
    assert (await c.items("series"))[0]["title"] == "A"
    assert (await c.item("series", 1))["id"] == 1
    assert await c.item("series", 2) is None
    assert await c.rename_preview("series", 1) == []
    assert route.calls.last.request.url.params["seriesId"] == "1"
    await c.rename_preview("movie", 7)
    assert route.calls.last.request.url.params["movieId"] == "7"
