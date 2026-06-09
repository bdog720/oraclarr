from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind


async def diagnose(clients: dict[str, BaseClient], title: str) -> dict:
    arr = arr_clients(clients, None)
    matches: list[dict] = []
    for c in arr.values():
        try:
            lib = await c.lookup_library(title, media_kind(c))
        except Exception:
            continue
        for item in lib:
            sid = item.get("id")
            try:
                queue = await c.queue()
            except Exception:
                queue = []
            try:
                missing = await c.wanted_missing()
            except Exception:
                missing = []
            id_key = "seriesId" if c.type == "sonarr" else "movieId"
            matches.append({
                "instance": c.name,
                "title": item.get("title"),
                "tvdb_id": item.get("tvdbId"),
                "tmdb_id": item.get("tmdbId"),
                "imdb_id": item.get("imdbId"),
                "in_library": True,
                "in_queue": any(q.get(id_key) == sid for q in queue),
                "wanted": any(
                    m.get(id_key) == sid or m.get("title") == item.get("title")
                    for m in missing
                ),
            })
    return {"query": title, "matches": matches}
