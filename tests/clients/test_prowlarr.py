import httpx, respx
from oraclarr_mcp.clients.prowlarr import ProwlarrClient
from oraclarr_mcp.clients.base import ApiKeyHeaderAuth

@respx.mock
async def test_indexers_and_stats():
    respx.get("http://h/api/v1/indexer").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "nyaa", "enable": True}]))
    respx.get("http://h/api/v1/health").mock(return_value=httpx.Response(200, json=[]))
    c = ProwlarrClient("prowlarr", "prowlarr", "http://h", ApiKeyHeaderAuth("K"), timeout=5)
    idx = await c.indexers()
    assert idx[0]["name"] == "nyaa"
    assert await c.health() == []
    await c.aclose()
