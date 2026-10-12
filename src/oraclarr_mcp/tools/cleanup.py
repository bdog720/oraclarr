import asyncio
from ..clients.base import BaseClient
from ..clients.cleanuparr import CLEANER_NAMES
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 100
SUMMARY_RECENT = 5
SUMMARY_STRIKES = 100
SECTIONS = ("config", "jobs", "rules", "strikes")

# Every projection below is an allowlist. Cleanuparr's config also holds the download
# client's host, username and password, and an auth block; none of it may leave here.


def _job(j: dict) -> dict:
    return {"name": j.get("name"), "status": j.get("status"), "schedule": j.get("schedule"),
            "last_run": j.get("previousRunTime"), "next_run": j.get("nextRunTime")}


def _recent(s: dict) -> dict:
    return {"type": s.get("type"), "title": s.get("title"), "at": s.get("createdAt"),
            "dry_run": s.get("isDryRun")}


def strike_row(s: dict) -> dict:
    return {"download_id": s.get("downloadId"), "title": s.get("title"),
            "total_strikes": s.get("totalStrikes"), "by_type": s.get("strikesByType") or {},
            "first_at": s.get("firstStrikeAt"), "latest_at": s.get("latestStrikeAt"),
            "marked_for_removal": s.get("isMarkedForRemoval"), "removed": s.get("isRemoved"),
            "dry_run": s.get("hasDryRunStrikes")}


def _download_client(c: dict) -> dict:
    return {"name": c.get("name"), "type": c.get("typeName"), "enabled": c.get("enabled")}


def _seeding_rule(r: dict) -> dict:
    return {"name": r.get("name"), "privacy": r.get("privacyType"),
            "categories": r.get("categories"), "tracker_patterns": r.get("trackerPatterns"),
            "max_ratio": r.get("maxRatio"), "min_seed_hours": r.get("minSeedTime"),
            "max_seed_hours": r.get("maxSeedTime"), "min_seeders": r.get("minSeeders"),
            "max_inactive_days": r.get("maxInactiveDays"), "action": r.get("action"),
            "delete_source_files": r.get("deleteSourceFiles")}


def _unlinked(u: dict) -> dict:
    return {"enabled": u.get("enabled"), "target_category": u.get("targetCategory"),
            "use_tag": u.get("useTag"), "categories": u.get("categories"),
            "ignored_root_dirs": u.get("ignoredRootDirs")}


def _queue_rule(r: dict, slow: bool = False) -> dict:
    out = {"name": r.get("name"), "enabled": r.get("enabled"),
           "max_strikes": r.get("maxStrikes"), "privacy": r.get("privacyType"),
           "min_completion": r.get("minCompletionPercentage"),
           "max_completion": r.get("maxCompletionPercentage"),
           "reset_on_progress": r.get("resetStrikesOnProgress")}
    if slow:
        out.update(min_speed=r.get("minSpeed"), max_time_hours=r.get("maxTimeHours"),
                   ignore_above_size=r.get("ignoreAboveSize"))
    return out


def _failed_import(queue_cleaner: dict) -> dict:
    f = queue_cleaner.get("failedImport") or {}
    return {"max_strikes": f.get("maxStrikes"), "ignore_private": f.get("ignorePrivate"),
            "delete_private": f.get("deletePrivate"), "patterns": f.get("patterns"),
            "pattern_mode": f.get("patternMode")}


def _cleaner(name: str, cfg: dict) -> dict:
    if name == "seeker":
        return {"enabled": cfg.get("searchEnabled"), "interval_minutes": cfg.get("searchInterval")}
    return {"enabled": cfg.get("enabled"), "schedule": cfg.get("cronExpression")}


async def _rules(c: BaseClient) -> dict:
    clients, stall, slow, queue_cleaner = await asyncio.gather(
        c.download_clients(), c.stall_rules(), c.slow_rules(), c.cleaner_config("queue_cleaner"))

    async def per_client(dc: dict) -> dict:
        seeding, unlinked = await asyncio.gather(c.seeding_rules(dc.get("id")),
                                                 c.unlinked_config(dc.get("id")))
        return {"client": _download_client(dc),
                "seeding_rules": [_seeding_rule(r) for r in seeding or []],
                "unlinked": _unlinked(unlinked or {})}

    per = await asyncio.gather(*(per_client(dc) for dc in clients))
    return {"clients": list(per),
            "stall_rules": [_queue_rule(r) for r in stall or []],
            "slow_rules": [_queue_rule(r, slow=True) for r in slow or []],
            "failed_import": _failed_import(queue_cleaner or {})}


async def _config(c: BaseClient) -> dict:
    general, *cleaners = await asyncio.gather(
        c.general(), *(c.cleaner_config(n) for n in CLEANER_NAMES))
    return {"dry_run": general.get("dryRun"),
            "strike_inactivity_hours": general.get("strikeInactivityWindowHours"),
            "history_retention_days": general.get("historyRetentionDays"),
            "ignored_downloads": len(general.get("ignoredDownloads") or []),
            "cleaners": {n: _cleaner(n, cfg or {}) for n, cfg in zip(CLEANER_NAMES, cleaners)}}


async def get_cleanup(clients: dict[str, BaseClient], section: str | None = None,
                      limit: int = 20) -> list[dict] | dict:
    if section is not None and section not in SECTIONS:
        return {"error": "invalid_section", "valid": list(SECTIONS)}
    limit = clamp(limit, MAX_LIMIT)
    sel = {n: c for n, c in clients.items() if c.type == "cleanuparr"}

    async def collect(c: BaseClient) -> Bounded | list | dict:
        if section == "rules":
            return await _rules(c)
        if section == "config":
            return await _config(c)
        if section == "jobs":
            return [_job(j) for j in await c.jobs()]
        if section == "strikes":
            items, total = await c.strikes(limit)
            return bounded([strike_row(s) for s in items], limit, total)
        general, jobs, (items, total), recent = await asyncio.gather(
            c.general(), c.jobs(), c.strikes(SUMMARY_STRIKES), c.recent_strikes())
        newest = sorted(recent or [], key=lambda s: s.get("createdAt") or "", reverse=True)
        return {"dry_run": general.get("dryRun"),
                "jobs": [_job(j) for j in jobs],
                # downloads is Cleanuparr's total (removed history included); the counts
                # below cover only the scanned rows, and complete says whether that is all.
                "strikes": {"downloads": total,
                            "scanned": len(items),
                            "complete": total <= len(items),
                            "active": sum(1 for s in items if not s.get("isRemoved")),
                            "marked_for_removal": sum(1 for s in items
                                                      if s.get("isMarkedForRemoval")),
                            "recent": [_recent(s) for s in newest[:SUMMARY_RECENT]]}}

    return await fan_out(sel, collect)
