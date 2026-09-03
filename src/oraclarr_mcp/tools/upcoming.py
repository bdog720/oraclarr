from datetime import date, timedelta
from ..clients.base import BaseClient
from ._arr import arr_clients
from ._util import fan_out

MIN_DAYS = 1
MAX_DAYS = 90

# Sonarr and Sportarr date episodes with airDateUtc. Radarr has no airDate at
# all, so fall back through its release fields in order of usefulness.
_WHEN_KEYS = ("airDateUtc", "digitalRelease", "physicalRelease", "inCinemas", "releaseDate")


def _when(rec: dict) -> str | None:
    for key in _WHEN_KEYS:
        value = rec.get(key)
        if value:
            return value
    return None


def _normalise(rec: dict) -> dict:
    parent = rec.get("series") or {}
    return {
        "title": rec.get("title"),
        "parent": parent.get("title"),
        "when": _when(rec),
        "monitored": bool(rec.get("monitored")),
        "has_file": bool(rec.get("hasFile")),
    }


async def get_upcoming(clients: dict[str, BaseClient], service: str | None = None,
                       days: int = 7) -> list[dict]:
    days = max(MIN_DAYS, min(MAX_DAYS, days))
    start = date.today()
    end = start + timedelta(days=days)

    async def collect(c: BaseClient) -> list[dict]:
        records = await c.calendar(start.isoformat(), end.isoformat())
        return [_normalise(r) for r in records]

    return await fan_out(arr_clients(clients, service), collect)
