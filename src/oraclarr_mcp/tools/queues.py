import asyncio
from ..clients.base import BaseClient
from ..models import ARR_TYPES
from ._util import clamp, probe

MAX_LIMIT = 500


async def get_queues(clients: dict[str, BaseClient], service: str | None = None,
                     limit: int = 100) -> dict:
    limit = clamp(limit, MAX_LIMIT)
    arr = {n: c for n, c in clients.items() if c.type in ARR_TYPES}
    if service is not None:
        arr = {n: c for n, c in arr.items() if n == service}
    qbits = {n: c for n, c in clients.items() if c.type == "qbittorrent"}

    qbit_results, arr_results = await asyncio.gather(
        asyncio.gather(*(probe(c, lambda x: x.torrents()) for c in qbits.values())),
        asyncio.gather(*(probe(c, lambda x: x.queue()) for c in arr.values())),
    )

    torrents_by_hash: dict[str, dict] = {}
    for r in qbit_results:
        if r.status == "ok":
            for t in r.data:
                torrents_by_hash[str(t.get("hash", "")).lower()] = t

    items: list[dict] = []
    for r in arr_results:
        if r.status != "ok":
            continue
        for rec in r.data:
            dl = str(rec.get("downloadId", "")).lower()
            t = torrents_by_hash.get(dl)
            size = rec.get("size") or 0
            left = rec.get("sizeleft") or 0
            pct = round(100 * (1 - left / size), 1) if size else None
            items.append({
                "instance": r.instance,
                "title": rec.get("title"),
                "state": rec.get("trackedDownloadState") or rec.get("status"),
                "percent": pct,
                "stalled": (t or {}).get("state", "").startswith("stalled"),
                "qbit": ({"state": t.get("state"), "progress": t.get("progress")} if t else None),
            })
    errors = [r.model_dump() for r in (*arr_results, *qbit_results) if r.status != "ok"]
    return {"items": items[:limit], "total": len(items), "truncated": len(items) > limit,
            "errors": errors}
