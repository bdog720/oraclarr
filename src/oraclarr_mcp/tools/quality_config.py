from ..clients.base import BaseClient
from ._util import probe

async def _arr_config(c: BaseClient) -> dict:
    out = {"profiles": await c.quality_profiles(),
           "custom_formats": await c.custom_formats()}
    try:
        out["release_profiles"] = await c.release_profiles()  # sonarr only
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

async def get_quality_config(clients: dict[str, BaseClient], service: str | None = None) -> list[dict]:
    sel = {n: c for n, c in clients.items() if c.type in ("sonarr", "radarr", "profilarr")}
    if service is not None:
        sel = {n: c for n, c in sel.items() if n == service}
    results = []
    for c in sel.values():
        fn = _profilarr_config if c.type == "profilarr" else _arr_config
        results.append((await probe(c, fn)).model_dump())
    return results
