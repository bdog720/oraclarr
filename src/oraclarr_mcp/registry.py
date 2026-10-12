from .config import Config, Instance
from .models import ARR_TYPES
from .clients.base import BaseClient, ApiKeyHeaderAuth, MediaBrowserTokenAuth, NoAuth
from .clients.arr import ArrClient
from .clients.prowlarr import ProwlarrClient
from .clients.qbittorrent import QbitClient, QbitCookieAuth
from .clients.tdarr import TdarrClient
from .clients.profilarr import ProfilarrClient
from .clients.jellyfin import JellyfinClient
from .clients.cleanuparr import CleanuparrClient
from .clients.netdata import NetdataClient

def _make(name: str, inst: Instance, timeout: int) -> BaseClient:
    t = inst.type
    if t in ARR_TYPES:
        return ArrClient(name, t, inst.url, ApiKeyHeaderAuth(inst.api_key or ""), timeout)
    if t == "prowlarr":
        return ProwlarrClient(name, t, inst.url, ApiKeyHeaderAuth(inst.api_key or ""), timeout)
    if t == "qbittorrent":
        return QbitClient(name, t, inst.url, QbitCookieAuth(inst.username or "", inst.password or ""), timeout)
    if t == "tdarr":
        return TdarrClient(name, t, inst.url, NoAuth(), timeout)
    if t == "profilarr":
        return ProfilarrClient(name, t, inst.url, ApiKeyHeaderAuth(inst.api_key or ""), timeout)
    if t == "jellyfin":
        return JellyfinClient(name, t, inst.url, MediaBrowserTokenAuth(inst.api_key or ""),
                              timeout)
    if t == "cleanuparr":
        return CleanuparrClient(name, t, inst.url, ApiKeyHeaderAuth(inst.api_key or ""), timeout)
    if t == "netdata":
        return NetdataClient(name, t, inst.url, NoAuth(), timeout)
    raise ValueError(f"unknown instance type {t}")

def build_clients(cfg: Config) -> dict[str, BaseClient]:
    out: dict[str, BaseClient] = {}
    for name, inst in cfg.instances.items():
        if inst.enabled:
            out[name] = _make(name, inst, cfg.defaults.timeout_seconds)
    return out

def clients_of_type(clients: dict[str, BaseClient], *types: str) -> dict[str, BaseClient]:
    return {n: c for n, c in clients.items() if c.type in types}
