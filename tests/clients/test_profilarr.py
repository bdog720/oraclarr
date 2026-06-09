import json
from pathlib import Path

import httpx
import respx
from oraclarr_mcp.clients.profilarr import ProfilarrClient
from oraclarr_mcp.clients.base import ApiKeyHeaderAuth

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _client():
    return ProfilarrClient("profilarr", "profilarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5)


@respx.mock
async def test_arr_instances():
    payload = json.loads((FIXTURES / "profilarr_arr.json").read_text())
    respx.get("http://h/api/v1/arr").mock(return_value=httpx.Response(200, json=payload))
    c = _client()
    insts = await c.arr_instances()
    assert [i["name"] for i in insts] == ["Radarr", "Sonarr", "Sonarr_Anime"]
    await c.aclose()


@respx.mock
async def test_status_returns_sync_state():
    payload = json.loads((FIXTURES / "profilarr_status.json").read_text())
    respx.get("http://h/api/v1/status").mock(return_value=httpx.Response(200, json=payload))
    c = _client()
    status = await c.status()
    assert status["version"] == "2.0.8"
    assert status["databases"][0]["counts"]["qualityProfiles"] == 11
    assert status["arrs"][0]["name"] == "Radarr"
    await c.aclose()
