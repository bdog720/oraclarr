import asyncio
from collections import Counter
from datetime import datetime, timezone

from ..clients.base import BaseClient
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 200
RECENT_ALERTS = 5
SECTIONS = ("alerts", "datasets", "disks")
NA = "not_available"
MIB = 2**20
GIB = 2**30
TIB = 2**40
HOST_TYPES = ("netdata", "truenas")
NETDATA_CONTEXTS = ("system.cpu", "system.load", "system.io_some_pressure", "system.ram",
                    "mem.available", "mem.swap", "zfs.arc_size")
GPU_CONTEXTS = ("nvidia_smi.gpu_temperature", "nvidia_smi.gpu_power_draw",
                "nvidia_smi.gpu_frame_buffer_memory_usage", "nvidia_smi.gpu_utilization",
                "nvidia_smi.gpu_encoder_utilization")

# Allowlists only: TrueNAS system info carries the serial and hostname, disk identifiers
# carry serials, Netdata labels carry the GPU UUID and node GUID.


def _gib(value, unit: int = 1):
    return None if value is None else round(value * unit / GIB, 1)


def _iso(d) -> str | None:
    ms = d.get("$date") if isinstance(d, dict) else None
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cpu(cpu: dict, load: dict, pressure: dict):
    if not cpu:
        return NA
    return {"busy_pct": round(sum(v for k, v in cpu.items() if k != "iowait"), 1),
            "iowait_pct": round(cpu.get("iowait") or 0, 1),
            "load": [round(load[k], 2) for k in ("load1", "load5", "load15")] if load else None,
            "io_pressure_pct": pressure.get("some 60") if pressure else None}


def _memory(ram: dict, avail: dict):
    if not ram:
        return NA
    total = sum(ram.get(k) or 0 for k in ("free", "used", "cached", "buffers"))
    return {"total_gib": _gib(total, MIB), "free_gib": _gib(ram.get("free"), MIB),
            "used_gib": _gib(ram.get("used"), MIB), "cached_gib": _gib(ram.get("cached"), MIB),
            "available_gib": _gib(avail.get("avail"), MIB) if avail else None}


def _swap(swap: dict):
    if not swap:
        return NA
    return {"used_gib": _gib(swap.get("used"), MIB), "free_gib": _gib(swap.get("free"), MIB)}


def _arc(arc: dict):
    if not arc:
        return NA
    size, top = arc.get("arcsz"), arc.get("max (high water)")
    return {"size_gib": _gib(size, MIB), "target_gib": _gib(arc.get("target"), MIB),
            "max_gib": _gib(top, MIB), "min_gib": _gib(arc.get("min (hard limit)"), MIB),
            "at_max": bool(size is not None and top and size >= 0.98 * top)}


def _gpus(temps, power, fb, util, enc):
    if not temps:
        return NA
    rows = []
    for i, t in enumerate(temps):
        def at(lst):
            return lst[i] if i < len(lst) else {}
        f = at(fb)
        rows.append({"temp_c": t.get("temperature"), "power_w": at(power).get("power_draw"),
                     "vram_used_gib": _gib(f.get("used")), "vram_free_gib": _gib(f.get("free")),
                     "util_pct": at(util).get("gpu"), "encoder_pct": at(enc).get("encoder")})
    return rows


async def _netdata_summary(c) -> dict:
    (cpu, load, pressure, ram, avail, swap, arc), gpu = await asyncio.gather(
        asyncio.gather(*(c.latest(x) for x in NETDATA_CONTEXTS)),
        asyncio.gather(*(c.latest_by_instance(x) for x in GPU_CONTEXTS)))
    return {"cpu": _cpu(cpu, load, pressure), "memory": _memory(ram, avail),
            "swap": _swap(swap), "arc": _arc(arc), "gpu": _gpus(*gpu)}


def _pool(p: dict) -> dict:
    size, scan = p.get("size") or 0, p.get("scan") or {}
    try:
        frag = int(p.get("fragmentation"))
    except (TypeError, ValueError):
        frag = None
    return {"name": p.get("name"), "status": p.get("status"), "healthy": p.get("healthy"),
            "used_pct": round((p.get("allocated") or 0) / size * 100, 1) if size else None,
            "free_tib": round((p.get("free") or 0) / TIB, 2), "fragmentation_pct": frag,
            "last_scrub": {"state": scan.get("state"), "errors": scan.get("errors"),
                           "finished": _iso(scan.get("end_time"))} if scan else None}


def _active(alerts: list[dict]) -> list[dict]:
    live = [a for a in alerts or [] if not a.get("dismissed")]
    return sorted(live, key=lambda a: (a.get("datetime") or {}).get("$date") or 0, reverse=True)


def _alert(a: dict) -> dict:
    return {"level": a.get("level"), "text": a.get("formatted"), "class": a.get("klass"),
            "since": _iso(a.get("datetime"))}


def _parsed(prop):
    return prop.get("parsed") if isinstance(prop, dict) else prop


def dataset_row(d: dict) -> dict:
    quota = _parsed(d.get("quota"))
    return {"name": d.get("id"), "used_gib": _gib(_parsed(d.get("used"))),
            "available_gib": _gib(_parsed(d.get("available"))),
            "quota_gib": _gib(quota) if quota else None}


def _disk(item: dict) -> dict:
    parts = [p.strip() for p in (item.get("identifier") or "").split("|")]
    fields = dict(p.split(": ", 1) for p in parts[1:] if ": " in p)
    return {"device": parts[0] or None, "type": fields.get("Type"),
            "model": fields.get("Model"), "temp_c": item.get("temp_c")}


async def _truenas_summary(c) -> dict:
    info, pools, alerts = await asyncio.gather(c.system_info(), c.pools(), c.alerts())
    active = _active(alerts)
    return {"system": {"version": info.get("version"),
                       "uptime_hours": round((info.get("uptime_seconds") or 0) / 3600, 1)},
            "pools": [_pool(p) for p in pools or []],
            "alerts": {"counts": dict(Counter(a.get("level") for a in active)),
                       "recent": [{k: v for k, v in _alert(a).items() if k != "class"}
                                  for a in active[:RECENT_ALERTS]]}}


async def get_host(clients: dict[str, BaseClient], section: str | None = None,
                   limit: int = 50) -> list[dict] | dict:
    if section is not None and section not in SECTIONS:
        return {"error": "invalid_section", "valid": list(SECTIONS)}
    limit = clamp(limit, MAX_LIMIT)
    types = HOST_TYPES if section is None else ("truenas",)
    sel = {n: c for n, c in clients.items() if c.type in types}

    async def collect(c) -> Bounded | list | dict:
        if c.type == "netdata":
            return await _netdata_summary(c)
        if section is None:
            return await _truenas_summary(c)
        if section == "datasets":
            rows = sorted((dataset_row(d) for d in await c.datasets()),
                          key=lambda r: r["used_gib"] or 0, reverse=True)
            return bounded(rows, limit)
        if section == "disks":
            return [_disk(x) for x in await c.disk_temps()]
        return bounded([_alert(a) for a in _active(await c.alerts())], limit)

    return await fan_out(sel, collect)
