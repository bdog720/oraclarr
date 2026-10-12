import difflib
import json
import re
import time
from datetime import datetime, timezone

from ..clients.base import BaseClient
from ..clients.docker import demux
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 200
SECTIONS = ("logs",)
HEALTH_OUTPUT_CHARS = 300
PROJECT = "com.docker.compose.project"
SERVICE = "com.docker.compose.service"
STATES = ("running", "exited", "created", "restarting", "paused", "dead")
_HEALTH_RE = re.compile(r"\((healthy|unhealthy|health: starting)\)")
_EXIT_RE = re.compile(r"^Exited \((-?\d+)\)")
MAX_LINES = 200
MAX_LINE_CHARS = 400
MAX_LINE_BYTES = 600  # JSON-escaped; non-ASCII and control chars expand up to 12x
MATCH_WINDOW = 2000
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SINCE_RE = re.compile(r"^(\d+)([mhd])$")
_UNIT_S = {"m": 60, "h": 3600, "d": 86400}

# Allowlist projections only. The client already dropped Env, Mounts and other
# labels; rows never carry a container ID.


def iso_seconds(t: str | None) -> str | None:
    if not t or t.startswith("0001-01-01"):
        return None
    return t[:19] + "Z"


def _name(x: dict) -> str | None:
    names = x.get("Names") or []
    return names[0].lstrip("/") if names else None


def _list_health(status: str | None) -> str | None:
    m = _HEALTH_RE.search(status or "")
    if not m:
        return None
    return "starting" if m.group(1) == "health: starting" else m.group(1)


def _list_exit(status: str | None) -> int | None:
    m = _EXIT_RE.match(status or "")
    return int(m.group(1)) if m else None


def _ports(x: dict) -> list[int]:
    return sorted({p["PublicPort"] for p in x.get("Ports") or [] if p.get("PublicPort")})


def container_row(x: dict, d: dict | None) -> dict:
    st = (d or {}).get("State") or {}
    state = x.get("State")
    labels = x.get("Labels") or {}
    if d is not None:
        health = (st.get("Health") or {}).get("Status")
        exit_code = st.get("ExitCode") if state in ("exited", "dead") else None
    else:
        health = _list_health(x.get("Status"))
        exit_code = _list_exit(x.get("Status"))
    row = {"name": _name(x), "stack": labels.get(PROJECT), "service": labels.get(SERVICE),
           "state": state, "health": health, "status": x.get("Status"),
           "restart_count": d.get("RestartCount") if d is not None else None,
           "exit_code": exit_code,
           "oom_killed": st.get("OOMKilled") if d is not None else None,
           "started_at": iso_seconds(st.get("StartedAt")),
           "finished_at": iso_seconds(st.get("FinishedAt")),
           "image": (x.get("Image") or "").split("@")[0] or None,
           "ports": _ports(x)}
    row["problem"] = bool(health == "unhealthy" or state in ("restarting", "dead")
                          or row["oom_killed"]
                          or (state == "exited" and exit_code not in (None, 0)))
    return row


def container_counts(rows: list[dict], with_problems: bool = True) -> dict:
    counts = {s: 0 for s in STATES}
    counts["unhealthy"] = 0
    for r in rows:
        if r["state"] in counts:
            counts[r["state"]] += 1
        if r["health"] == "unhealthy":
            counts["unhealthy"] += 1
    if with_problems:
        counts["problems"] = sum(1 for r in rows if r["problem"])
    return counts


def find_container(listing: list[dict], name: str) -> tuple[dict | None, dict | None]:
    key = name.strip().lstrip("/").lower()
    for pick in (lambda x: (_name(x) or "").lower(),
                 lambda x: ((x.get("Labels") or {}).get(SERVICE) or "").lower()):
        hit = next((x for x in listing if pick(x) == key), None)
        if hit is not None:
            return hit, None
    names = sorted(n for n in (_name(x) for x in listing) if n)
    return None, {"error": "not_found", "name": name,
                  "suggestions": difflib.get_close_matches(name.lower(), names, n=5,
                                                           cutoff=0.3)}


def _network(mode: str | None, listing: list[dict]) -> str | None:
    if mode and mode.startswith("container:"):
        ref = mode.split(":", 1)[1]
        target = next((x for x in listing if ref in (x.get("Id"), _name(x))), None)
        return f"container:{_name(target)}" if target else "container:unknown"
    return mode


def _sort_key(row: dict) -> tuple:
    return (not row["problem"], row["name"] or "")


async def _summary(c, limit: int) -> Bounded:
    listing = await c.containers()
    details = await c.inspect_many([x["Id"] for x in listing])
    rows = sorted((container_row(x, d) for x, d in zip(listing, details)), key=_sort_key)
    b = bounded(rows, limit)
    return Bounded(data={"counts": container_counts(rows), "containers": b.data},
                   total=b.total, truncated=b.truncated)


async def _detail(c, name: str) -> dict:
    listing = await c.containers()
    x, miss = find_container(listing, name)
    if miss:
        return miss
    d = await c.inspect(x["Id"])
    if d is None:
        return {"error": "not_found", "name": name, "suggestions": []}
    row = container_row(x, d)
    health = (d.get("State") or {}).get("Health") or {}
    log = health.get("Log") or []
    row["health_detail"] = {
        "status": health.get("Status"), "failing_streak": health.get("FailingStreak"),
        "last_output": (log[-1].get("Output") or "").strip()[:HEALTH_OUTPUT_CHARS]
        if log else None} if health else None
    host = d.get("HostConfig") or {}
    row["restart_policy"] = (host.get("RestartPolicy") or {}).get("Name")
    row["network"] = _network(host.get("NetworkMode"), listing)
    return row


def parse_since(value: str, now: float) -> int:
    v = value.strip()
    m = _SINCE_RE.match(v.lower())
    if m:
        return int(now - int(m.group(1)) * _UNIT_S[m.group(2)])
    t = datetime.fromisoformat(v)  # raises ValueError on anything else, including ""
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp())


def _cut(text: str) -> str:
    text = _ANSI_RE.sub("", text)[:MAX_LINE_CHARS]
    while len(json.dumps(text)) > MAX_LINE_BYTES:
        text = text[:len(text) * 3 // 4]
    return text


def _parse_line(stream: str, raw: str) -> tuple[str | None, str, str]:
    ts, sep, text = raw.partition(" ")
    if sep and ts[:4].isdigit() and "T" in ts:
        return iso_seconds(ts), stream, text
    return None, stream, raw


async def _logs(c, name: str, lines: int, since_ts: int | None, match: str | None) -> dict:
    listing = await c.containers()
    x, miss = find_container(listing, name)
    if miss:
        return miss
    d = await c.inspect(x["Id"])
    if d is None:
        return {"error": "not_found", "name": name, "suggestions": []}
    tty = bool((d.get("Config") or {}).get("Tty"))
    raw = await c.logs(x["Id"], MATCH_WINDOW if match else lines, since_ts)
    parsed = [_parse_line(s, line) for s, line in demux(raw, tty)]
    result: dict = {"container": _name(x)}
    if match:
        needle = match.lower()
        parsed = [p for p in parsed if needle in p[2].lower()]
        result["matched_of"] = len(parsed)
        result["truncated"] = len(parsed) > lines
    else:
        result["truncated"] = len(parsed) >= lines
    result["lines"] = [{"t": t, "stream": s, "text": _cut(text)}
                       for t, s, text in parsed[-lines:]]
    return result


async def get_containers(clients: dict[str, BaseClient], name: str | None = None,
                         section: str | None = None, lines: int = 50, since: str | None = None,
                         match: str | None = None, limit: int = 100) -> list[dict] | dict:
    if section is not None and section not in SECTIONS:
        return {"error": "invalid_section", "valid": list(SECTIONS)}
    if section == "logs" and not name:
        return {"error": "name_required"}
    since_ts = None
    if section == "logs" and since:
        try:
            since_ts = parse_since(since, time.time())
        except ValueError:
            return {"error": "invalid_since", "expected": "<n>m, <n>h, <n>d or ISO 8601"}
    limit = clamp(limit, MAX_LIMIT)
    lines = clamp(lines, MAX_LINES)
    sel = {n: c for n, c in clients.items() if c.type == "docker"}

    async def collect(c):
        if section == "logs":
            return await _logs(c, name, lines, since_ts, match)
        if name:
            return await _detail(c, name)
        return await _summary(c, limit)

    return await fan_out(sel, collect)
