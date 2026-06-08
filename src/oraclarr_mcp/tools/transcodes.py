from ..clients.base import BaseClient
from ._util import fan_out

async def get_transcodes(clients: dict[str, BaseClient]) -> list[dict]:
    sel = {n: c for n, c in clients.items() if c.type == "tdarr"}
    async def collect(c):
        return {"status": await c.status(), "nodes": await c.nodes(), "staged": await c.staged()}
    return await fan_out(sel, collect)
