import httpx, respx
from oraclarr_mcp.clients.tdarr import TdarrClient
from oraclarr_mcp.clients.base import NoAuth

def _client():
    return TdarrClient("tdarr", "tdarr", "http://h", NoAuth(), timeout=5)

@respx.mock
async def test_nodes():
    respx.get("http://h/api/v2/get-nodes").mock(
        return_value=httpx.Response(200, json={"node1": {"nodeName": "n1", "workers": {}}}))
    c = _client()
    nodes = await c.nodes()
    assert "node1" in nodes
    await c.aclose()

@respx.mock
async def test_status():
    respx.get("http://h/api/v2/status").mock(
        return_value=httpx.Response(200, json={"status": "ok"}))
    c = _client()
    assert (await c.status())["status"] == "ok"
    await c.aclose()
