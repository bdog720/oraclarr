from ..clients.base import BaseClient
from ._util import Bounded, clamp, fan_out

MAX_LIMIT = 200


def _staged(i: dict) -> dict:
    # A live staged item carries ~55 KB of flowPluginHandler/ffprobe state; Tdarr's
    # _id is the file path.
    return {"file": i.get("_id"), "status": i.get("status"),
            "worker_type": i.get("workerType"), "node": i.get("nodeID"),
            "started": i.get("start")}


async def get_transcodes(clients: dict[str, BaseClient], limit: int = 50) -> list[dict]:
    limit = clamp(limit, MAX_LIMIT)
    sel = {n: c for n, c in clients.items() if c.type == "tdarr"}

    async def collect(c) -> Bounded:
        staged = await c.staged()
        kept = [_staged(i) for i in staged[:limit]]
        data = {"status": await c.status(), "nodes": await c.nodes(),
                "staged_count": len(staged), "staged": kept}
        return Bounded(data=data, total=len(staged), truncated=len(staged) > len(kept))

    return await fan_out(sel, collect)
