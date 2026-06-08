from ..clients.base import BaseClient
from ._util import fan_out

async def get_indexers(clients: dict[str, BaseClient]) -> list[dict]:
    sel = {n: c for n, c in clients.items() if c.type == "prowlarr"}
    async def collect(c):
        return {"indexers": await c.indexers(), "stats": await c.indexer_stats()}
    return await fan_out(sel, collect)
