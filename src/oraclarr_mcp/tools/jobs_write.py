"""start_job: gated, two-step writes that start arr commands or a Jellyfin scan."""
import hashlib
import json

from ..audit import audit
from ..plans import PLAN_TTL_S, Plan, PlanStore
from ._arr import media_kind
from ._util import probe

TOOL = "start_job"
ACTIONS = ("refresh", "rescan", "search", "rename", "scan")
ARR_ACTIONS = ("refresh", "rescan", "search", "rename")
WRITE_ARR_TYPES = ("sonarr", "radarr")
MAX_PREVIEW_ROWS = 50
MAX_CANDIDATES = 10
COMMAND_PATH = "/api/v3/command"
REFRESH_PARAMS = {"Recursive": "true", "MetadataRefreshMode": "Default",
                  "ImageRefreshMode": "Default", "ReplaceAllMetadata": "false",
                  "ReplaceAllImages": "false"}


def _err(error: str, **kw) -> dict:
    return {"error": error, **kw}


def _target(item: dict, kind: str) -> dict:
    return {"title": item.get("title"), "year": item.get("year"), "id": item.get("id"),
            "path": item.get("path"), "kind": kind}


def _request(path: str, json_body=None, params=None) -> dict:
    return {"method": "POST", "path": path, "json": json_body, "params": params}


async def _resolve(c, kind: str, target: str) -> tuple[dict | None, dict | None]:
    t = target.strip()
    if t.lower().startswith("id:"):
        try:
            item_id = int(t[3:])
        except ValueError:
            return None, _err("not_found", target=target)
        item = await c.item(kind, item_id)
        return (item, None) if item else (None, _err("not_found", target=target))
    low = t.lower()
    items = await c.items(kind)
    hits = ([i for i in items if (i.get("title") or "").lower() == low]
            or [i for i in items if low in (i.get("title") or "").lower()])
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, _err("not_found", target=target)
    return None, _err("ambiguous", target=target, candidates=[
        {"title": i.get("title"), "year": i.get("year"), "id": i.get("id")}
        for i in hits[:MAX_CANDIDATES]])


def _arr_body(action: str, kind: str, item_id: int, season, files) -> dict:
    series = kind == "series"
    if action == "refresh":
        return ({"name": "RefreshSeries", "seriesId": item_id} if series
                else {"name": "RefreshMovie", "movieIds": [item_id]})
    if action == "rescan":
        return ({"name": "RescanSeries", "seriesId": item_id} if series
                else {"name": "RescanMovie", "movieId": item_id})
    if action == "search":
        if not series:
            return {"name": "MoviesSearch", "movieIds": [item_id]}
        if season is not None:
            return {"name": "SeasonSearch", "seriesId": item_id, "seasonNumber": season}
        return {"name": "SeriesSearch", "seriesId": item_id}
    return {"name": "RenameFiles", ("seriesId" if series else "movieId"): item_id,
            "files": files}


def _file_id(row: dict):
    return row.get("episodeFileId", row.get("movieFileId"))


def _search_preview(item: dict, kind: str, season) -> dict | None:
    if kind == "movie":
        return {"monitored": item.get("monitored"), "has_file": item.get("hasFile")}
    stats, extra = item.get("statistics") or {}, {}
    monitored = item.get("monitored")
    if season is not None:
        s = next((x for x in item.get("seasons") or [] if x.get("seasonNumber") == season),
                 None)
        if s is None:
            return None
        stats, monitored, extra = s.get("statistics") or {}, s.get("monitored"), {"season": season}
    total, have = stats.get("episodeCount") or 0, stats.get("episodeFileCount") or 0
    return {"monitored": monitored, "episodes": total, "with_files": have,
            "missing": max(0, total - have), **extra}


async def _arr_plan(c, service, action, target, season):
    kind = media_kind(c)
    item, miss = await _resolve(c, kind, target)
    if miss:
        return None, miss
    item_id = item.get("id")
    preview, files = {}, None
    fingerprint = f"{kind}:{item_id}"
    if action == "search":
        preview = _search_preview(item, kind, season)
        if preview is None:
            return None, _err("not_found", target=target, season=season)
    if action == "rename":
        rows = await c.rename_preview(kind, item_id)
        if not rows:
            return None, {"nothing_to_do": True, "target": _target(item, kind)}
        files = sorted({f for f in (_file_id(r) for r in rows) if f is not None})
        preview = {"count": len(rows), "rows": [
            {"existing": r.get("existingPath"), "new": r.get("newPath")}
            for r in rows[:MAX_PREVIEW_ROWS]]}
        canon = sorted(json.dumps([_file_id(r), r.get("existingPath"), r.get("newPath")])
                       for r in rows)
        fingerprint = hashlib.sha256("\n".join(canon).encode()).hexdigest()
    body = _arr_body(action, kind, item_id, season, files)
    return Plan(tool=TOOL, instance=service, action=action,
                args={"action": action, "target": f"id:{item_id}", "season": season,
                      "library": None},
                request=_request(COMMAND_PATH, body), preview=preview,
                fingerprint=fingerprint, target=_target(item, kind)), None


async def _scan_plan(c, service, library):
    tasks, folders = await c.scheduled_tasks(), await c.virtual_folders()
    task = next((t for t in tasks if t.get("Key") == "RefreshLibrary"), None)
    names = [f.get("Name") for f in folders]
    scanning = bool(task and task.get("State") not in (None, "Idle"))
    if library is not None:
        lib = next((f for f in folders if (f.get("Name") or "").lower() == library.lower()),
                   None)
        if lib is None:
            return None, _err("not_found", library=library, valid=names)
        return Plan(tool=TOOL, instance=service, action="scan",
                    args={"action": "scan", "target": None, "season": None,
                          "library": library},
                    request=_request(f"/Items/{lib.get('ItemId')}/Refresh",
                                     params=dict(REFRESH_PARAMS)),
                    preview={"libraries": [lib.get("Name")], "scanning": scanning},
                    fingerprint=f"library:{lib.get('ItemId')}"), None
    if task is None:
        return None, _err("not_supported", detail="no RefreshLibrary task on this server")
    return Plan(tool=TOOL, instance=service, action="scan",
                args={"action": "scan", "target": None, "season": None, "library": None},
                request=_request(f"/ScheduledTasks/Running/{task.get('Id')}"),
                preview={"libraries": names, "scanning": scanning},
                fingerprint=f"task:{task.get('Id')}"), None


async def build_plan(c, service, action, target, season, library):
    if action == "scan":
        return await _scan_plan(c, service, library)
    return await _arr_plan(c, service, action, target, season)


def plan_view(plan: Plan) -> dict:
    return {"instance": plan.instance, "action": plan.action, "target": plan.target,
            "request": plan.request, "preview": plan.preview}


def _validate(clients, action, service, target, season, library) -> dict | None:
    if action not in ACTIONS:
        return _err("invalid_action", valid=list(ACTIONS))
    c = clients.get(service) if service else None
    if c is None:
        return _err("invalid_service", valid=sorted(clients))
    if c.type == "sportarr":
        return _err("not_supported", instance=service,
                    detail="Sportarr does not implement the command API")
    if action in ARR_ACTIONS and c.type not in WRITE_ARR_TYPES:
        return _err("invalid_service", detail=f"{action} needs a sonarr or radarr instance")
    if action == "scan" and c.type != "jellyfin":
        return _err("invalid_service", detail="scan needs a jellyfin instance")
    if action in ARR_ACTIONS and not target:
        return _err("target_required")
    if season is not None and not (action == "search" and c.type == "sonarr"):
        return _err("invalid_argument", detail="season only applies to a Sonarr search")
    if library is not None and action != "scan":
        return _err("invalid_argument", detail="library only applies to scan")
    return None


async def _dry_run(clients, store, writable, action, service, target, season, library):
    bad = _validate(clients, action, service, target, season, library)
    if bad:
        return bad
    if service not in writable:
        audit("refused", tool=TOOL, instance=service, action=action,
              detail="writes_not_allowed")
        return _err("writes_not_allowed", instance=service)
    res = await probe(clients[service],
                      lambda c: build_plan(c, service, action, target, season, library))
    if res.status != "ok":
        return _err(res.status, instance=service, detail=res.error)
    plan, out = res.data
    if plan is None:
        return out
    pid = store.add(plan)
    audit("planned", tool=TOOL, instance=service, action=action,
          target=(plan.target or {}).get("id"), plan_id=pid)
    return {"plan_id": pid, "expires_in_s": PLAN_TTL_S, "plan": plan_view(plan)}


async def start_job(clients: dict, store: PlanStore, writable: set[str], action: str,
                    service: str | None = None, target: str | None = None,
                    season: int | None = None, library: str | None = None,
                    plan_id: str | None = None) -> dict:
    return await _dry_run(clients, store, writable, action, service, target, season,
                          library)
