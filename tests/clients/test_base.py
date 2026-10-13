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


@respx.mock
async def test_post_returns_json_or_none_and_raises_on_error():
    respx.post("http://h/a").mock(return_value=httpx.Response(201, json={"id": 5}))
    respx.post("http://h/b").mock(return_value=httpx.Response(204))
    respx.post("http://h/c").mock(return_value=httpx.Response(400, json={"message": "bad"}))
    c = BaseClient("x", "x", "http://h", NoAuth(), timeout=5)
    assert await c.post("/a", json={"name": "X"}) == {"id": 5}
    assert respx.calls[0].request.content == b'{"name":"X"}'
    assert await c.post("/b", params={"Recursive": "true"}) is None
    assert respx.calls[1].request.url.params["Recursive"] == "true"
    with pytest.raises(httpx.HTTPStatusError):
        await c.post("/c")
