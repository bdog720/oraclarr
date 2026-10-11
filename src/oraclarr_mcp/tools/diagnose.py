import asyncio
from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind
from ._util import Bounded, bounded, merge_matches, probe

MAX_ITEMS = 20


async def diagnose(clients: dict[str, BaseClient], title: str) -> dict:
    async def per_instance(c: BaseClient) -> Bounded:
        kind = media_kind(c)
        lib = await c.lookup_library(title, kind)
        if not lib:
            return bounded([], MAX_ITEMS)
        # Fetched once per instance, not once per matched item. A failure in one
        # of them leaves that flag unknown (None) instead of dropping the match.
        queue, missing = await asyncio.gather(c.queue(), c.wanted_missing(),
                                              return_exceptions=True)
        id_key = "seriesId" if kind == "series" else "movieId"
        rows = []
        for item in lib:
            row = {
                "instance": c.name,
                "title": item.get("title"),
                "tvdb_id": item.get("tvdbId"),
                "tmdb_id": item.get("tmdbId"),
                "imdb_id": item.get("imdbId"),
                "in_library": True,
            }
            if isinstance(queue, BaseException):
                row["in_queue"] = None
                row["queue_error"] = str(queue)
            else:
                row["in_queue"] = any(q.get(id_key) == item.get("id") for q in queue)
            if isinstance(missing, BaseException):
                row["wanted"] = None
                row["wanted_error"] = str(missing)
            else:
                row["wanted"] = any(
                    m.get(id_key) == item.get("id") or m.get("title") == item.get("title")
                    for m in missing
                )
            rows.append(row)
        return bounded(rows, MAX_ITEMS)

    arr = arr_clients(clients, None)
    results = await asyncio.gather(*(probe(c, per_instance) for c in arr.values()))
    return merge_matches(title, list(results))
