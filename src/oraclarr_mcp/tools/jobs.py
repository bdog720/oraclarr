import asyncio
import re

from ..clients.base import BaseClient
from ..redact import scrub_text
from ._arr import arr_clients
from ._util import Bounded, bounded, clamp, fan_out
from .library import _notable, _task

MAX_LIMIT = 50
MESSAGE_CHARS = 300
SECTIONS = ("schedule",)
ACTIVE = ("queued", "started")
FAILED = ("failed", "aborted", "orphaned", "cancelled")
ROUTINE = frozenset({"RefreshMonitoredDownloads", "ProcessMonitoredDownloads",
                     "MessagingCleanup", "CheckHealth", "Housekeeping",
                     "CleanUpRecycleBin", "ApplicationUpdateCheck"})
NOTE = "finished commands are kept by the arr for a few minutes only"
NOT_SUPPORTED = {"not_supported": "Sportarr does not implement /api/v3/command"}
_DURATION_RE = re.compile(r"^(?:(\d+)\.)?(\d+):(\d+):(\d+(?:\.\d+)?)$")


def duration_s(value) -> float | None:
    """.NET TimeSpan text ("[d.]hh:mm:ss[.fffffff]") -> seconds."""
    m = _DURATION_RE.match(value or "")
    if not m:
        return None
    days, hours, minutes, seconds = m.groups()
    total = int(days or 0) * 86400 + int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return round(total, 3)


def _ids(body: dict, single: str, many: str) -> list[int]:
    ids = list(body.get(many) or [])
    if body.get(single) is not None:
        ids.insert(0, body[single])
    return [i for i in ids if isinstance(i, int) and not isinstance(i, bool)]


async def _items(c, body: dict) -> dict | None:
    """Allowlisted body keys only: what media a command works on."""
    series = _ids(body, "seriesId", "seriesIds")
    movies = _ids(body, "movieId", "movieIds")
    if body.get("files") is not None and series:
        return {"kind": "file", "count": len(body["files"]),
                "titles": await c.titles("series", series[:1])}
    if body.get("episodeIds"):
        return {"kind": "episode", "count": len(body["episodeIds"]),
                "titles": await c.titles("series", series[:1]) if series else []}
    if series:
        return {"kind": "series", "count": len(series),
                "titles": await c.titles("series", series)}
    if movies:
        return {"kind": "movie", "count": len(movies),
                "titles": await c.titles("movie", movies)}
    return None


async def _command(c, cmd: dict) -> dict:
    msg = cmd.get("message")
    return {"id": cmd.get("id"), "name": cmd.get("commandName") or cmd.get("name"),
            "status": cmd.get("status"), "result": cmd.get("result"),
            "trigger": cmd.get("trigger"), "queued": cmd.get("queued"),
            "started": cmd.get("started"), "ended": cmd.get("ended"),
            "duration_s": duration_s(cmd.get("duration")),
            # Redact before the cut: a cut secret no longer matches the full value.
            "message": scrub_text(msg)[:MESSAGE_CHARS] if msg else None,
            "items": await _items(c, cmd.get("body") or {})}


def _newest(cmd: dict) -> str:
    return cmd.get("ended") or cmd.get("started") or cmd.get("queued") or ""


async def _arr_summary(c, include_routine: bool, limit: int) -> Bounded:
    cmds = await c.commands()
    # Running before queued: the arr may list a long queue ahead of the running command.
    active = sorted((x for x in cmds if x.get("status") in ACTIVE),
                    key=lambda x: x.get("status") != "started")
    failed = [x for x in cmds if x.get("status") in FAILED]
    recent = sorted((x for x in cmds if x.get("status") not in ACTIVE + FAILED
                     and (include_routine or x.get("name") not in ROUTINE)),
                    key=_newest, reverse=True)
    # `limit` caps the rows per instance; active jobs are the most useful, then failures.
    a_rows = active[:limit]
    f_rows = failed[:limit - len(a_rows)]
    groups = [a_rows, f_rows, recent[:limit - len(a_rows) - len(f_rows)]]
    a, f, r = await asyncio.gather(*(asyncio.gather(*(_command(c, x) for x in g))
                                     for g in groups))
    counts = {"active": len(active), "failed": len(failed), "recent": len(recent)}
    total = sum(counts.values())
    shown = sum(len(g) for g in groups)
    return Bounded(data={"active": list(a), "failed": list(f), "recent": list(r),
                         "counts": counts, "note": NOTE},
                   total=total, truncated=shown < total)



def _schedule_row(t: dict) -> dict:
    return {"name": t.get("name"), "interval_min": t.get("interval"),
            "last_run": t.get("lastExecution"), "next_run": t.get("nextExecution"),
            "last_duration_s": duration_s(t.get("lastDuration"))}


async def _schedule(c, limit: int) -> Bounded:
    rows = sorted((_schedule_row(t) for t in await c.system_tasks()),
                  key=lambda r: r["next_run"] or "~")
    return bounded(rows, limit)

async def get_jobs(clients: dict[str, BaseClient], service: str | None = None,
                   section: str | None = None, include_routine: bool = False,
                   limit: int = 50) -> list[dict] | dict:
    if section is not None and section not in SECTIONS:
        return {"error": "invalid_section", "valid": list(SECTIONS)}
    limit = clamp(limit, MAX_LIMIT)
    sel = dict(arr_clients(clients, None))
    if section is None:
        sel.update({n: c for n, c in clients.items() if c.type == "jellyfin"})
    if service is not None:
        sel = {n: c for n, c in sel.items() if n == service}

    async def collect(c):
        if c.type == "sportarr":
            return dict(NOT_SUPPORTED)
        if c.type == "jellyfin":
            return {"tasks": [_task(t) for t in await c.scheduled_tasks() if _notable(t)]}
        if section == "schedule":
            return await _schedule(c, limit)
        return await _arr_summary(c, include_routine, limit)

    return await fan_out(sel, collect)
