import asyncio
from typing import Any, Awaitable, Callable
from ..clients.base import BaseClient
from ..errors import status_for_exception
from ..models import InstanceResult

async def probe(client: BaseClient, fn: Callable[[BaseClient], Awaitable[Any]]) -> InstanceResult:
    try:
        data = await fn(client)
        return InstanceResult(instance=client.name, type=client.type, status="ok", data=data)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not hard-fail
        return InstanceResult(instance=client.name, type=client.type,
                              status=status_for_exception(exc), error=str(exc))

async def fan_out(clients: dict[str, BaseClient],
                  fn: Callable[[BaseClient], Awaitable[Any]]) -> list[dict]:
    results = await asyncio.gather(*(probe(c, fn) for c in clients.values()))
    return [r.model_dump() for r in results]
