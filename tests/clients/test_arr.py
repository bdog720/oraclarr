import json
import httpx
import respx
from pathlib import Path
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
