from ..clients.base import BaseClient
from ._util import probe

async def get_queues(clients: dict[str, BaseClient], service: str | None = None) -> dict:
    arr = {n: c for n, c in clients.items() if c.type in ("sonarr", "radarr")}
    if service is not None:
        arr = {n: c for n, c in arr.items() if n == service}
    qbits = {n: c for n, c in clients.items() if c.type == "qbittorrent"}

    torrents_by_hash: dict[str, dict] = {}
    qbit_errors = []
    for c in qbits.values():
        r = await probe(c, lambda x: x.torrents())
        if r.status == "ok":
            for t in r.data:
                torrents_by_hash[str(t.get("hash", "")).lower()] = t
        else:
            qbit_errors.append(r.model_dump())

    items: list[dict] = []
    arr_errors = []
    for c in arr.values():
        r = await probe(c, lambda x: x.queue())
        if r.status != "ok":
            arr_errors.append(r.model_dump())
            continue
        for rec in r.data:
            dl = str(rec.get("downloadId", "")).lower()
            t = torrents_by_hash.get(dl)
            size = rec.get("size") or 0
            left = rec.get("sizeleft") or 0
            pct = round(100 * (1 - left / size), 1) if size else None
            items.append({
                "instance": c.name,
                "title": rec.get("title"),
                "state": rec.get("trackedDownloadState") or rec.get("status"),
                "percent": pct,
                "stalled": (t or {}).get("state", "").startswith("stalled"),
                "qbit": ({"state": t.get("state"), "progress": t.get("progress")} if t else None),
            })
    return {"items": items, "errors": arr_errors + qbit_errors}
