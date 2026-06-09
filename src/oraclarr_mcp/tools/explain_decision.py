from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind

async def explain_decision(clients: dict[str, BaseClient], title: str) -> dict:
    arr = arr_clients(clients, None)
    matches: list[dict] = []
    for c in arr.values():
        try:
            lib = await c.lookup_library(title, media_kind(c))
        except Exception:
            continue
        if not lib:
            continue
        try:
            profiles = {p["id"]: p for p in await c.quality_profiles()}
        except Exception:
            profiles = {}
        kind = media_kind(c)
        for item in lib:
            if title.lower() not in item.get("title", "").lower():
                continue
            prof = profiles.get(item.get("qualityProfileId"), {})
            try:
                history = await c.item_history(item.get("id"), kind)
            except Exception:
                history = []
            grabs = [
                {"release": h.get("sourceTitle"),
                 "score": h.get("customFormatScore"),
                 "formats": [f.get("name") for f in h.get("customFormats", [])]}
                for h in history
                if h.get("eventType") == "grabbed"
            ]
            matches.append({
                "instance": c.name,
                "title": item.get("title"),
                "profile": {
                    "name": prof.get("name"),
                    "cutoff": prof.get("cutoff"),
                    "min_format_score": prof.get("minFormatScore"),
                    "cutoff_format_score": prof.get("cutoffFormatScore"),
                    "format_scores": [{"name": f.get("name"), "score": f.get("score")}
                                      for f in prof.get("formatItems", [])],
                },
                "recent_grabs": grabs,
            })
    return {"query": title, "matches": matches}
