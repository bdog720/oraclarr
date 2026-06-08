from ..clients.base import BaseClient

async def _summary(c: BaseClient) -> dict:
    if c.type in ("sonarr", "radarr"):
        return {"version": (await c.system_status()).get("version"),
                "warnings": [h.get("message") for h in await c.health()],
                "disks": await c.diskspace()}
    if c.type == "prowlarr":
        return {"version": (await c.system_status()).get("version"),
                "warnings": [h.get("message") for h in await c.health()]}
    if c.type == "qbittorrent":
        return await c.transfer_info()
    if c.type == "tdarr":
        return {"status": await c.status(), "nodes": list((await c.nodes()).keys())}
    if c.type == "profilarr":
        return {"instances": await c.arr_instances()}
    return {}

async def stack_health(clients: dict[str, BaseClient]) -> list[dict]:
    from ._util import fan_out
    return await fan_out(clients, _summary)
