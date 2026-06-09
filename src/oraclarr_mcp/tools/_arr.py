from ..clients.base import BaseClient

def arr_clients(clients: dict[str, BaseClient], service: str | None) -> dict[str, BaseClient]:
    sel = {n: c for n, c in clients.items() if c.type in ("sonarr", "radarr")}
    if service is not None:
        sel = {n: c for n, c in sel.items() if n == service}
    return sel

def media_kind(client: BaseClient) -> str:
    return "movie" if client.type == "radarr" else "series"
