from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind
from ._util import fan_out

async def search_media(clients: dict[str, BaseClient], term: str) -> list[dict]:
    sel = arr_clients(clients, None)
    return await fan_out(sel, lambda c: c.lookup_library(term, media_kind(c)))
