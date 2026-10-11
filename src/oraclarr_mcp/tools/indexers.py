from ..clients.base import BaseClient
from ._util import fan_out


def _indexer(i: dict) -> dict:
    return {"name": i.get("name"), "enabled": i.get("enable"),
            "protocol": i.get("protocol"), "priority": i.get("priority")}


def _stat(s: dict) -> dict:
    return {"name": s.get("indexerName"), "queries": s.get("numberOfQueries"),
            "grabs": s.get("numberOfGrabs"), "failed_queries": s.get("numberOfFailedQueries"),
            "failed_grabs": s.get("numberOfFailedGrabs"),
            "avg_response_ms": s.get("averageResponseTime")}


async def get_indexers(clients: dict[str, BaseClient]) -> list[dict]:
    sel = {n: c for n, c in clients.items() if c.type == "prowlarr"}

    async def collect(c):
        stats = await c.indexer_stats()
        return {"indexers": [_indexer(i) for i in await c.indexers()],
                "stats": [_stat(s) for s in (stats or {}).get("indexers", [])]}

    return await fan_out(sel, collect)
