import asyncio
from ..clients.base import BaseClient
from ._arr import arr_clients
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 200


def _wanted(r: dict, reason: str) -> dict:
    return {
        "title": r.get("title"),
        "parent": (r.get("series") or {}).get("title"),
        "season": r.get("seasonNumber"),
        "episode": r.get("episodeNumber"),
        "air_date": r.get("airDateUtc") or r.get("digitalRelease") or r.get("inCinemas"),
        "monitored": bool(r.get("monitored")),
        "reason": reason,
    }


async def get_wanted(clients: dict[str, BaseClient], service: str | None = None,
                     limit: int = 50) -> list[dict]:
    limit = clamp(limit, MAX_LIMIT)

    async def collect(c: BaseClient) -> Bounded:
        (missing, m_total), (cutoff, c_total) = await asyncio.gather(
            c.wanted_page("missing", limit), c.wanted_page("cutoff", limit))
        rows = ([_wanted(r, "missing") for r in missing]
                + [_wanted(r, "cutoff") for r in cutoff])
        return bounded(rows, limit, m_total + c_total)

    return await fan_out(arr_clients(clients, service), collect)
