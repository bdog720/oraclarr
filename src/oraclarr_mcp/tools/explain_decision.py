import asyncio
from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind
from ._util import Bounded, bounded, merge_matches, probe

# Each examined item costs one history request; a broad title must not fan out
# into hundreds of calls against an I/O-bound server.
MAX_ITEMS = 10


def _profile_view(prof: dict) -> dict:
    return {
        "name": prof.get("name"),
        "cutoff": prof.get("cutoff"),
        "min_format_score": prof.get("minFormatScore"),
        "cutoff_format_score": prof.get("cutoffFormatScore"),
        "format_scores": [{"name": f.get("name"), "score": f.get("score")}
                          for f in prof.get("formatItems", [])],
    }


def _grabs(history: list[dict]) -> list[dict]:
    return [
        {"release": h.get("sourceTitle"),
         "score": h.get("customFormatScore"),
         "formats": [f.get("name") for f in h.get("customFormats", [])]}
        for h in history
        if h.get("eventType") == "grabbed"
    ]


async def explain_decision(clients: dict[str, BaseClient], title: str) -> dict:
    async def per_instance(c: BaseClient) -> Bounded:
        kind = media_kind(c)
        lib = [i for i in await c.lookup_library(title, kind)
               if title.lower() in i.get("title", "").lower()]
        if not lib:
            return bounded([], MAX_ITEMS)
        kept = lib[:MAX_ITEMS]
        profiles = {p["id"]: p for p in await c.quality_profiles()}
        histories = await asyncio.gather(*(c.item_history(i.get("id"), kind) for i in kept))
        rows = [{
            "instance": c.name,
            "title": item.get("title"),
            "profile": _profile_view(profiles.get(item.get("qualityProfileId"), {})),
            "recent_grabs": _grabs(history),
        } for item, history in zip(kept, histories)]
        return bounded(rows, MAX_ITEMS, total=len(lib))

    arr = arr_clients(clients, None)
    results = await asyncio.gather(*(probe(c, per_instance) for c in arr.values()))
    return merge_matches(title, list(results))
