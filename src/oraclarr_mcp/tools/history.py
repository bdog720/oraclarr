from ..clients.base import BaseClient
from ._arr import arr_clients
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 200


def _event(r: dict) -> dict:
    parent = r.get("series") or r.get("movie") or {}
    quality = (r.get("quality") or {}).get("quality") or {}
    return {
        "date": r.get("date"),
        "event_type": r.get("eventType"),
        "source_title": r.get("sourceTitle"),
        "title": parent.get("title"),
        "quality": quality.get("name"),
        "custom_format_score": r.get("customFormatScore"),
        "download_id": r.get("downloadId"),
    }


async def get_history(clients: dict[str, BaseClient], service: str | None = None,
                      limit: int = 30) -> list[dict]:
    limit = clamp(limit, MAX_LIMIT)

    async def collect(c: BaseClient) -> Bounded:
        records, total = await c.history_page(limit)
        return bounded([_event(r) for r in records], limit, total)

    return await fan_out(arr_clients(clients, service), collect)
