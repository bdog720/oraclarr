import asyncio
from ..clients.base import BaseClient
from ..models import ARR_TYPES
from ._util import probe


def _profile(p: dict) -> dict:
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "cutoff": p.get("cutoff"),
        "upgrade_allowed": p.get("upgradeAllowed"),
        "min_format_score": p.get("minFormatScore"),
        "cutoff_format_score": p.get("cutoffFormatScore"),
        # Zero-score formats are most of the list and change nothing.
        "format_scores": [{"name": f.get("name"), "score": f.get("score")}
                          for f in p.get("formatItems", []) if f.get("score")],
    }


def _release_profile(r: dict) -> dict:
    return {"name": r.get("name"), "enabled": r.get("enabled"),
            "required": r.get("required"), "ignored": r.get("ignored")}


async def _arr_config(c: BaseClient) -> dict:
    out = {"profiles": [_profile(p) for p in await c.quality_profiles()],
           "custom_formats": [{"id": f.get("id"), "name": f.get("name")}
                              for f in await c.custom_formats()]}
    try:
        out["release_profiles"] = [_release_profile(r)
                                   for r in await c.release_profiles()]  # sonarr only
    except Exception:
        out["release_profiles"] = []
    return out


async def _profilarr_config(c: BaseClient) -> dict:
    s = await c.status()
    return {
        "version": s.get("version"),
        "databases": s.get("databases", []),
        "arrs": s.get("arrs", []),
    }


async def get_quality_config(clients: dict[str, BaseClient],
                             service: str | None = None) -> list[dict]:
    sel = {n: c for n, c in clients.items() if c.type in (*ARR_TYPES, "profilarr")}
    if service is not None:
        sel = {n: c for n, c in sel.items() if n == service}
    results = await asyncio.gather(*(
        probe(c, _profilarr_config if c.type == "profilarr" else _arr_config)
        for c in sel.values()
    ))
    return [r.model_dump() for r in results]
