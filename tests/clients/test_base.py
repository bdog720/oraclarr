import httpx
import respx
import pytest
from oraclarr_mcp.clients.base import BaseClient, ApiKeyHeaderAuth, NoAuth

@respx.mock
async def test_get_sends_api_key_header_and_returns_json():
    route = respx.get("http://h/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={"version": "4.0"}))
    c = BaseClient("sonarr", "sonarr", "http://h", ApiKeyHeaderAuth("KEY"), timeout=5)
    data = await c.get_json("/api/v3/system/status")
    assert data == {"version": "4.0"}
    assert route.calls.last.request.headers["X-Api-Key"] == "KEY"
    await c.aclose()

@respx.mock
async def test_get_json_raises_on_500():
    respx.get("http://h/x").mock(return_value=httpx.Response(500))
    c = BaseClient("t", "tdarr", "http://h", NoAuth(), timeout=5)
    with pytest.raises(httpx.HTTPStatusError):
        await c.get_json("/x")
    await c.aclose()
