import httpx
import respx
from oraclarr_mcp.clients.profilarr import ProfilarrClient
from oraclarr_mcp.clients.base import ApiKeyHeaderAuth

def _client():
    return ProfilarrClient("profilarr", "profilarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5)

@respx.mock
async def test_arr_instances():
    respx.get("http://h/api/arr").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "radarr"}]))
    c = _client()
    assert (await c.arr_instances())[0]["name"] == "radarr"
    await c.aclose()
