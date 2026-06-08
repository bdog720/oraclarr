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
