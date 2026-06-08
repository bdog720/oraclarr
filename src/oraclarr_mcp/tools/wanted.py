from ..clients.base import BaseClient
from ._arr import arr_clients
from ._util import fan_out

async def get_wanted(clients: dict[str, BaseClient], service: str | None = None) -> list[dict]:
    sel = arr_clients(clients, service)
    async def both(c):
        return (await c.wanted_missing()) + (await c.wanted_cutoff())
    return await fan_out(sel, both)
