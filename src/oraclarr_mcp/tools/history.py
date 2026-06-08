from ..clients.base import BaseClient
from ._arr import arr_clients
from ._util import fan_out

async def get_history(clients: dict[str, BaseClient], service: str | None = None, limit: int = 30) -> list[dict]:
    sel = arr_clients(clients, service)
    return await fan_out(sel, lambda c: c.history(limit))
