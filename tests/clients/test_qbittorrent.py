import httpx, respx
from oraclarr_mcp.clients.qbittorrent import QbitClient, QbitCookieAuth

def _client():
    auth = QbitCookieAuth("user", "pass")
    return QbitClient("qbit", "qbittorrent", "http://h", auth, timeout=5)

@respx.mock
async def test_login_then_torrents_info():
    respx.post("http://h/api/v2/auth/login").mock(
        return_value=httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=abc; path=/"}))
    respx.get("http://h/api/v2/torrents/info").mock(
        return_value=httpx.Response(200, json=[{"hash": "H1", "name": "t", "state": "downloading", "progress": 0.5}]))
    c = _client()
    rows = await c.torrents()
    assert rows[0]["hash"] == "H1"
    await c.aclose()

@respx.mock
async def test_transfer_info():
    respx.post("http://h/api/v2/auth/login").mock(
        return_value=httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=abc"}))
    respx.get("http://h/api/v2/transfer/info").mock(
        return_value=httpx.Response(200, json={"connection_status": "connected", "dl_info_speed": 1000}))
    c = _client()
    info = await c.transfer_info()
    assert info["connection_status"] == "connected"
    await c.aclose()
