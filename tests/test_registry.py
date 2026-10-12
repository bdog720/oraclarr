from oraclarr_mcp.config import Config, Instance, ServerSettings, Defaults
from oraclarr_mcp.registry import build_clients
from oraclarr_mcp.clients.arr import ArrClient
from oraclarr_mcp.clients.qbittorrent import QbitClient

def _cfg(instances):
    return Config(server=ServerSettings(), defaults=Defaults(), instances=instances)

async def test_build_clients_routes_types_and_skips_disabled():
    cfg = _cfg({
        "sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K"),
        "qbit": Instance(type="qbittorrent", url="http://h:8080", username="u", password="p"),
        "off": Instance(type="radarr", url="http://h:7878", api_key="K", enabled=False),
    })
    clients = build_clients(cfg)
    assert isinstance(clients["sonarr"], ArrClient)
    assert isinstance(clients["qbit"], QbitClient)
    assert "off" not in clients
    for c in clients.values():
        await c.aclose()


async def test_sportarr_routes_to_arr_client():
    cfg = _cfg({"sportarr": Instance(type="sportarr", url="http://h:1867", api_key="K")})
    clients = build_clients(cfg)
    c = clients["sportarr"]
    assert isinstance(c, ArrClient)
    assert c.type == "sportarr"
    await c.aclose()


async def test_jellyfin_routes_to_jellyfin_client():
    from oraclarr_mcp.clients.jellyfin import JellyfinClient
    cfg = _cfg({"jellyfin": Instance(type="jellyfin", url="http://h:8096", api_key="K")})
    c = build_clients(cfg)["jellyfin"]
    assert isinstance(c, JellyfinClient)
    assert c.auth.headers() == {"Authorization": 'MediaBrowser Token="K"'}
    await c.aclose()


async def test_cleanuparr_routes_to_cleanuparr_client():
    from oraclarr_mcp.clients.cleanuparr import CleanuparrClient
    cfg = _cfg({"cleanuparr": Instance(type="cleanuparr", url="http://h:11011", api_key="K")})
    c = build_clients(cfg)["cleanuparr"]
    assert isinstance(c, CleanuparrClient)
    assert c.auth.headers() == {"X-Api-Key": "K"}
    await c.aclose()


async def test_netdata_routes_to_netdata_client():
    from oraclarr_mcp.clients.netdata import NetdataClient
    cfg = _cfg({"netdata": Instance(type="netdata", url="http://h:20999")})
    c = build_clients(cfg)["netdata"]
    assert isinstance(c, NetdataClient)
    await c.aclose()


async def test_truenas_routes_to_truenas_client():
    from oraclarr_mcp.clients.truenas import TruenasClient
    cfg = _cfg({"truenas": Instance(type="truenas", url="https://h", api_key="K",
                                    verify_tls=False)})
    c = build_clients(cfg)["truenas"]
    assert isinstance(c, TruenasClient) and c.type == "truenas"
    await c.aclose()
