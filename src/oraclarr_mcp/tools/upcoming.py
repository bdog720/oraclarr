from datetime import date, timedelta
from ..clients.base import BaseClient
from ._arr import arr_clients
from ._util import Bounded, bounded, clamp, fan_out

MIN_DAYS = 1
MAX_DAYS = 90

# Sonarr and Sportarr date episodes with airDateUtc. Radarr has no airDate at
# all, so fall back through its release fields in order of usefulness.
_WHEN_KEYS = ("airDateUtc", "digitalRelease", "physicalRelease", "inCinemas", "releaseDate")


def _when(rec: dict, start: str, end: str) -> str | None:
    """The date that put this record in the calendar window.

    A Radarr movie carries up to four release dates, and the calendar matches
    on any of them. Reporting the first one present gives answers like a
    digitalRelease three months in the past inside a list of upcoming items,
    so prefer the earliest date that actually falls inside the window.
    """
    candidates = [rec[k] for k in _WHEN_KEYS if rec.get(k)]
    if not candidates:
        return None
    in_window = sorted(c for c in candidates if start <= c[:10] <= end)
    return in_window[0] if in_window else candidates[0]


def _normalise(rec: dict, start: str, end: str) -> dict:
    parent = rec.get("series") or {}
    return {
        "title": rec.get("title"),
        "parent": parent.get("title"),
        "when": _when(rec, start, end),
        "monitored": bool(rec.get("monitored")),
        "has_file": bool(rec.get("hasFile")),
    }


MAX_LIMIT = 200


async def get_upcoming(clients: dict[str, BaseClient], service: str | None = None,
                       days: int = 7, limit: int = 100) -> list[dict]:
    days = max(MIN_DAYS, min(MAX_DAYS, days))
    limit = clamp(limit, MAX_LIMIT)
    start = date.today()
    end = start + timedelta(days=days)

    async def collect(c: BaseClient) -> Bounded:
        lo, hi = start.isoformat(), end.isoformat()
        records = await c.calendar(lo, hi)
        return bounded([_normalise(r, lo, hi) for r in records], limit)

    return await fan_out(arr_clients(clients, service), collect)
