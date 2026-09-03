from ..clients.base import BaseClient
from ..models import ARR_TYPES

def arr_clients(clients: dict[str, BaseClient], service: str | None) -> dict[str, BaseClient]:
    sel = {n: c for n, c in clients.items() if c.type in ARR_TYPES}
    if service is not None:
        sel = {n: c for n, c in sel.items() if n == service}
    return sel

def media_kind(client: BaseClient) -> str:
    return "movie" if client.type == "radarr" else "series"
