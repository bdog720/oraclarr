import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from ..budget import remaining
from ..clients.base import BaseClient
from ..errors import status_for_exception
from ..models import InstanceResult


@dataclass
class Bounded:
    """A per-instance result cut to a limit. probe() copies total/truncated to the envelope."""
    data: Any
    total: int
    truncated: bool


def bounded(items: list, limit: int, total: int | None = None) -> Bounded:
    kept = items[:limit]
    # Upstream totals can be missing (0) or stale; never report fewer than we hold.
    total = max(len(items), total or 0)
    return Bounded(data=kept, total=total, truncated=total > len(kept))


def clamp(limit: int, maximum: int) -> int:
    return max(1, min(maximum, limit))


def _client_timeout(client: Any) -> float | None:
    http = getattr(client, "_http", None)
    return getattr(getattr(http, "timeout", None), "read", None)


async def probe(client: BaseClient, fn: Callable[[BaseClient], Awaitable[Any]]) -> InstanceResult:
    start = time.monotonic()
    left = remaining()
    try:
        if left is None:
            data = await fn(client)
        elif left <= 0:
            raise TimeoutError
        else:
            data = await asyncio.wait_for(fn(client), left)
    except TimeoutError:
        return InstanceResult(instance=client.name, type=client.type, status="timeout",
                              error="upstream_timeout",
                              after_s=round(time.monotonic() - start, 2))
    except Exception as exc:  # noqa: BLE001 - diagnostics must not hard-fail
        status = status_for_exception(exc)
        return InstanceResult(instance=client.name, type=client.type, status=status,
                              error=str(exc),
                              after_s=_client_timeout(client) if status == "timeout" else None)
    if isinstance(data, Bounded):
        return InstanceResult(instance=client.name, type=client.type, status="ok",
                              data=data.data, total=data.total, truncated=data.truncated)
    return InstanceResult(instance=client.name, type=client.type, status="ok", data=data)


async def fan_out(clients: dict[str, BaseClient],
                  fn: Callable[[BaseClient], Awaitable[Any]]) -> list[dict]:
    results = await asyncio.gather(*(probe(c, fn) for c in clients.values()))
    return [r.model_dump() for r in results]


def merge_matches(query: str, results: list[InstanceResult]) -> dict:
    """Flatten per-instance match lists into one answer; failed instances go to errors."""
    ok = [r for r in results if r.status == "ok"]
    return {
        "query": query,
        "matches": [m for r in ok for m in r.data],
        "truncated": any(r.truncated for r in ok),
        "errors": [r.model_dump() for r in results if r.status != "ok"],
    }
