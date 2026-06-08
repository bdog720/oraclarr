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
