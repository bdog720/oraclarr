import asyncio
from collections import Counter
from ..clients.base import BaseClient
from ..models import ARR_TYPES

async def _summary(c: BaseClient) -> dict:
    if c.type in ARR_TYPES:
        return {"version": (await c.system_status()).get("version"),
                "warnings": [h.get("message") for h in await c.health()],
                "disks": [{"path": d.get("path"), "free_space": d.get("freeSpace"),
                           "total_space": d.get("totalSpace")} for d in await c.diskspace()]}
    if c.type == "prowlarr":
        return {"version": (await c.system_status()).get("version"),
                "warnings": [h.get("message") for h in await c.health()]}
    if c.type == "qbittorrent":
        return await c.transfer_info()
    if c.type == "tdarr":
        return {"status": await c.status(), "nodes": list((await c.nodes()).keys())}
    if c.type == "profilarr":
        return {"instances": await c.arr_instances()}
    if c.type == "jellyfin":
        info, tasks = await asyncio.gather(c.system_info(), c.scheduled_tasks())
        return {"version": info.get("Version"),
                "pending_restart": info.get("HasPendingRestart"),
                "update_available": info.get("HasUpdateAvailable"),
                "failed_tasks": [t.get("Name") for t in tasks
                                 if (t.get("LastExecutionResult") or {}).get("Status") == "Failed"]}
    if c.type == "cleanuparr":
        general, jobs = await asyncio.gather(c.general(), c.jobs())
        return {"dry_run": general.get("dryRun"),
                # Live states: Scheduled, Running, Not Scheduled.
                "scheduled_jobs": [j.get("name") for j in jobs
                                   if j.get("status") != "Not Scheduled"],
                "unscheduled_jobs": [j.get("name") for j in jobs
                                     if j.get("status") == "Not Scheduled"]}
    if c.type == "netdata":
        info, cpu = await asyncio.gather(c.info(), c.latest("system.cpu"))
        return {"version": info.get("version"), "collecting": bool(cpu)}
    if c.type == "truenas":
        info, pools, alerts = await c.summary()  # one TrueNAS login, not three
        active = [a for a in alerts or [] if not a.get("dismissed")]
        return {"version": info.get("version"),
                "pools_healthy": all(p.get("healthy") for p in pools or []),
                "alerts": dict(Counter(a.get("level") for a in active))}
    if c.type == "docker":
        from .containers import container_counts, container_row
        version, listing = await asyncio.gather(c.version(), c.containers())
        rows = [container_row(x, None) for x in listing]
        return {"version": version.get("Version"),
                "containers": container_counts(rows, with_problems=False)}
    return {}

JOIN_STATUSES = ("unreachable", "timeout")


async def _join_containers(clients: dict[str, BaseClient], rows: list[dict]) -> None:
    """Attach container state to unreachable rows, matched by published port. Only with
    exactly one docker instance: with two hosts a port could match the wrong container."""
    from ._util import probe
    from .containers import containers_for_ports, instance_port
    dockers = [c for c in clients.values() if c.type == "docker"]
    if len(dockers) != 1:
        return
    want = {}
    for r in rows:
        if r["status"] in JOIN_STATUSES and r["type"] != "docker":
            port = instance_port(clients.get(r["instance"]))
            if port:
                want[r["instance"]] = port
    if not want:
        return
    res = await probe(dockers[0], lambda c: containers_for_ports(c, set(want.values())))
    if res.status != "ok":
        return
    for r in rows:
        if r["instance"] in want:
            r["container"] = res.data.get(want[r["instance"]])


async def stack_health(clients: dict[str, BaseClient]) -> list[dict]:
    from ._util import fan_out
    rows = await fan_out(clients, _summary)
    await _join_containers(clients, rows)
    return rows
