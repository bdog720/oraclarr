import asyncio
from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind
from ._util import Bounded, bounded, merge_matches, probe
from .library import search_row

MAX_ITEMS = 20
JELLYFIN_SEARCH_LIMIT = 50


def _arr_ids(match: dict) -> set[tuple[str, str]]:
    pairs = (("tvdb", match.get("tvdb_id")), ("tmdb", match.get("tmdb_id")),
             ("imdb", match.get("imdb_id")))
    # Sonarr reports tmdbId 0 when unknown; a zero id must never match.
    return {(k, str(v)) for k, v in pairs if v}


def _jellyfin_ids(items: list[dict]) -> set[tuple[str, str]]:
    out = set()
    for i in items:
        row = search_row(i)
        for k in ("tvdb", "tmdb", "imdb"):
            if row[f"{k}_id"]:
                out.add((k, str(row[f"{k}_id"])))
    return out


def _join_jellyfin(out: dict, results: list) -> None:
    ok = [r for r in results if r.status == "ok"]
    out["errors"].extend(r.model_dump() for r in results if r.status != "ok")
    known = set()
    for r in ok:
        items, _total = r.data
        known |= _jellyfin_ids(items)
    for m in out["matches"]:
        m["in_jellyfin"] = bool(_arr_ids(m) & known) if ok else None


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
    jf = {n: c for n, c in clients.items() if c.type == "jellyfin"}
    arr_results, jf_results = await asyncio.gather(
        asyncio.gather(*(probe(c, per_instance) for c in arr.values())),
        asyncio.gather(*(probe(c, lambda x: x.search_items(title, JELLYFIN_SEARCH_LIMIT))
                         for c in jf.values())),
    )
    out = merge_matches(title, list(arr_results))
    if jf:
        _join_jellyfin(out, list(jf_results))
    return out
