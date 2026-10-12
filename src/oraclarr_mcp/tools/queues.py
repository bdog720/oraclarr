import asyncio
from ..clients.base import BaseClient
from ..models import ARR_TYPES
from ._util import clamp, probe

# 400 x the 448-byte worst-case row (150-char title, qbit + strike join) stays under
# the 200 KB output cap; see test_limit_budget.
MAX_LIMIT = 400
CLEANUPARR_STRIKE_PAGE = 500


def _strike_summary(s: dict) -> dict:
    return {"strikes": s.get("totalStrikes") or 0, "by_type": s.get("strikesByType") or {},
            "marked_for_removal": bool(s.get("isMarkedForRemoval")),
            "dry_run": bool(s.get("hasDryRunStrikes"))}


async def _cleanuparr_lookup(c: BaseClient) -> tuple[dict, bool]:
    """Strike summaries by lowercased torrent hash, and whether the list was cut short.
    Parsing runs inside probe(), so a malformed reply fails only this instance."""
    items, total = await c.strikes(CLEANUPARR_STRIKE_PAGE)
    index = {str(s.get("downloadId") or "").lower(): _strike_summary(s) for s in items}
    index.pop("", None)
    return index, total > len(items)


async def get_queues(clients: dict[str, BaseClient], service: str | None = None,
                     limit: int = 100) -> dict:
    limit = clamp(limit, MAX_LIMIT)
    arr = {n: c for n, c in clients.items() if c.type in ARR_TYPES}
    if service is not None:
        arr = {n: c for n, c in arr.items() if n == service}
    qbits = {n: c for n, c in clients.items() if c.type == "qbittorrent"}

    cleans = {n: c for n, c in clients.items() if c.type == "cleanuparr"}
    qbit_results, arr_results, clean_results = await asyncio.gather(
        asyncio.gather(*(probe(c, lambda x: x.torrents()) for c in qbits.values())),
        asyncio.gather(*(probe(c, lambda x: x.queue_page(limit)) for c in arr.values())),
        asyncio.gather(*(probe(c, _cleanuparr_lookup) for c in cleans.values())),
    )
    clean_ok = [r for r in clean_results if r.status == "ok"]
    strike_index: dict[str, dict] = {}
    strikes_cut = False
    for r in clean_ok:
        index, cut = r.data
        strike_index.update(index)
        strikes_cut = strikes_cut or cut

    torrents_by_hash: dict[str, dict] = {}
    for r in qbit_results:
        if r.status == "ok":
            for t in r.data:
                torrents_by_hash[str(t.get("hash", "")).lower()] = t

    items: list[dict] = []
    upstream_total = 0
    for r in arr_results:
        if r.status != "ok":
            continue
        records, total = r.data
        upstream_total += max(total, len(records))
        for rec in records:
            dl = str(rec.get("downloadId", "")).lower()
            t = torrents_by_hash.get(dl)
            size = rec.get("size") or 0
            left = rec.get("sizeleft") or 0
            pct = round(100 * (1 - left / size), 1) if size else None
            item = {
                "instance": r.instance,
                "title": rec.get("title"),
                "state": rec.get("trackedDownloadState") or rec.get("status"),
                "percent": pct,
                "stalled": ((t or {}).get("state") or "").startswith("stalled"),
                "qbit": ({"state": t.get("state"), "progress": t.get("progress")} if t else None),
            }
            if cleans:
                if dl in strike_index:
                    item["cleanuparr"] = strike_index[dl]
                elif clean_ok and len(clean_ok) == len(clean_results) and not strikes_cut:
                    # Only a complete answer from every Cleanuparr proves "no strikes".
                    item["cleanuparr"] = {"strikes": 0}
                else:
                    item["cleanuparr"] = None
            items.append(item)
    errors = [r.model_dump() for r in (*arr_results, *qbit_results, *clean_results)
              if r.status != "ok"]
    kept = items[:limit]
    return {"items": kept, "total": upstream_total, "truncated": upstream_total > len(kept),
            "errors": errors}
