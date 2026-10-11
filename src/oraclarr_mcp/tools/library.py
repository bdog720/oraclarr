import asyncio
from ..clients.base import BaseClient
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 100
SUMMARY_RECENT = 10
SECTIONS = ("libraries", "recent", "sessions", "tasks")


def _library(v: dict, count: int) -> dict:
    progress = v.get("RefreshProgress")
    active = v.get("RefreshStatus") not in (None, "Idle")
    return {"name": v.get("Name"), "type": v.get("CollectionType"), "items": count,
            "scan": v.get("RefreshStatus"),
            "scan_progress": round(progress, 1) if active and progress is not None else None}


def _task(t: dict) -> dict:
    last = t.get("LastExecutionResult") or {}
    return {"name": t.get("Name"), "state": t.get("State"),
            "progress": t.get("CurrentProgressPercentage"),
            "last_status": last.get("Status"), "last_end": last.get("EndTimeUtc"),
            "last_error": last.get("ErrorMessage")}


def _notable(t: dict) -> bool:
    return (t.get("State") not in (None, "Idle")
            or (t.get("LastExecutionResult") or {}).get("Status") == "Failed")


def _session(s: dict) -> dict:
    now = s.get("NowPlayingItem") or {}
    play = s.get("PlayState") or {}
    tc = s.get("TranscodingInfo")
    return {
        "user": s.get("UserName"), "client": s.get("Client"), "device": s.get("DeviceName"),
        "item": now.get("Name"), "series": now.get("SeriesName"),
        "play_method": play.get("PlayMethod"), "paused": play.get("IsPaused"),
        "transcode": None if not tc else {
            "video_codec": tc.get("VideoCodec"), "audio_codec": tc.get("AudioCodec"),
            "container": tc.get("Container"), "hw": tc.get("HardwareAccelerationType"),
            "reasons": tc.get("TranscodeReasons"), "progress": tc.get("CompletionPercentage")},
    }


def _recent(i: dict) -> dict:
    return {"name": i.get("Name"), "type": i.get("Type"), "series": i.get("SeriesName"),
            "season": i.get("ParentIndexNumber"), "episode": i.get("IndexNumber"),
            "added": i.get("DateCreated")}


def search_row(i: dict) -> dict:
    ids = {k.lower(): v for k, v in (i.get("ProviderIds") or {}).items()}
    return {"name": i.get("Name"), "type": i.get("Type"), "year": i.get("ProductionYear"),
            "path": i.get("Path"), "tvdb_id": ids.get("tvdb"), "tmdb_id": ids.get("tmdb"),
            "imdb_id": ids.get("imdb"), "added": i.get("DateCreated")}


async def _libraries(c: BaseClient) -> list[dict]:
    folders = await c.virtual_folders()
    counts = await asyncio.gather(*(c.library_count(v.get("ItemId")) for v in folders))
    return [_library(v, n) for v, n in zip(folders, counts)]


async def get_library(clients: dict[str, BaseClient], section: str | None = None,
                      term: str | None = None, limit: int = 20) -> list[dict] | dict:
    if section is not None and section not in SECTIONS:
        return {"error": "invalid_section", "valid": list(SECTIONS)}
    limit = clamp(limit, MAX_LIMIT)
    sel = {n: c for n, c in clients.items() if c.type == "jellyfin"}

    async def collect(c: BaseClient) -> Bounded | list | dict:
        if term is not None:
            items, total = await c.search_items(term, limit)
            return bounded([search_row(i) for i in items], limit, total)
        if section == "libraries":
            return await _libraries(c)
        if section == "tasks":
            return bounded([_task(t) for t in await c.scheduled_tasks()], limit)
        if section == "sessions":
            return bounded([_session(s) for s in await c.sessions()], limit)
        if section == "recent":
            items, total = await c.recent_items(limit)
            return bounded([_recent(i) for i in items], limit, total)
        info, libs, tasks, sessions, (recent, _) = await asyncio.gather(
            c.system_info(), _libraries(c), c.scheduled_tasks(), c.sessions(),
            c.recent_items(SUMMARY_RECENT))
        return {"version": info.get("Version"), "pending_restart": info.get("HasPendingRestart"),
                "libraries": libs,
                "tasks": [_task(t) for t in tasks if _notable(t)],
                "sessions": [_session(s) for s in sessions if s.get("NowPlayingItem")],
                "recent": [_recent(i) for i in recent]}

    return await fan_out(sel, collect)
