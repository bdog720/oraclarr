from mcp.server.fastmcp import FastMCP
from .config import Config
from .clients.base import BaseClient
from .guards import tool_spec, enabled_for_toolsets, writable_instances, ToolSpec
from .call_guard import guarded
from .redact import Redactor
from .tools.health import stack_health
from .tools.queues import get_queues
from .tools.diagnose import diagnose
from .tools.explain_decision import explain_decision
from .tools.quality_config import get_quality_config
from .tools.history import get_history
from .tools.wanted import get_wanted
from .tools.search import search_media
from .tools.indexers import get_indexers
from .tools.transcodes import get_transcodes
from .tools.upcoming import get_upcoming
from .tools.library import get_library
from .tools.cleanup import get_cleanup
from .tools.host import get_host
from .tools.containers import get_containers
from .tools.jobs import get_jobs
from .plans import PlanStore
from .tools.jobs_write import start_job

TOOL_SPECS: list[ToolSpec] = [
    tool_spec("stack_health", "read", "always"),
    tool_spec("get_queues", "read", "downloads"),
    tool_spec("diagnose", "read", "media"),
    tool_spec("explain_decision", "read", "media"),
    tool_spec("get_quality_config", "read", "media"),
    tool_spec("get_history", "read", "media"),
    tool_spec("get_wanted", "read", "media"),
    tool_spec("search_media", "read", "media"),
    tool_spec("get_indexers", "read", "media"),
    tool_spec("get_transcodes", "read", "transcode"),
    tool_spec("get_upcoming", "read", "media"),
    tool_spec("get_library", "read", "library"),
    tool_spec("get_cleanup", "read", "downloads"),
    tool_spec("get_host", "read", "host"),
    tool_spec("get_containers", "read", "containers"),
    tool_spec("get_jobs", "read", "media"),
    tool_spec("start_job", "safe_write", "media"),
]


def build_server(
    cfg: Config,
    clients: dict[str, BaseClient],
    host: str = "127.0.0.1",
    port: int = 7979,
) -> FastMCP:
    mcp = FastMCP("oraclarr-mcp", host=host, port=port)
    enabled = set(enabled_for_toolsets(TOOL_SPECS, cfg.server.toolsets))
    spec_by_name = {s.name: s for s in TOOL_SPECS}
    redactor = Redactor.from_config(cfg)
    writable = writable_instances(cfg)
    plans = PlanStore()

    def register(name: str, fn):
        if name not in enabled:
            return
        if spec_by_name[name].risk != "read" and not writable:
            return  # writes off: the tool does not exist for clients
        mcp.tool(name=name)(guarded(
            name, fn,
            budget_s=cfg.server.tool_budget_seconds,
            max_bytes=cfg.server.max_output_bytes,
            redactor=redactor,
        ))

    async def _stack_health() -> list[dict]:
        """Health and status of every configured service: versions, warnings, disk space,
        Tdarr nodes, container counts. A service that is unreachable or timing out also
        shows its Docker container's state, exit code and restart count. Use this
        instead of `docker ps` or curling service APIs over SSH to check whether a
        service is up."""
        return await stack_health(clients)

    async def _get_queues(service: str | None = None, limit: int = 100) -> dict:
        """Unified active download queue: arr queues joined to qBittorrent torrents
        (progress, stalled). Use this instead of curling Sonarr/Radarr/qBittorrent over
        SSH. Returns at most `limit` items (max 400); `truncated` and `total` show when more
        exist."""
        return await get_queues(clients, service, limit)

    async def _diagnose(title: str) -> dict:
        """Trace one title through library, download queue, and wanted list on every arr
        instance. Use this instead of grepping arr config files for API keys and curling
        the APIs over SSH. Returns at most 20 matches per instance; `truncated` shows when
        more exist, and `errors` lists instances that failed or timed out."""
        return await diagnose(clients, title)

    async def _explain_decision(title: str) -> dict:
        """Explain why a title was grabbed or is being upgraded: quality profile, custom
        format scores, and grab history. Use this instead of querying arr databases over
        SSH. Examines at most 10 matching items per instance and returns the newest 10
        grabs of each (`grabs_total` gives the full count); `truncated` shows when more
        items matched."""
        return await explain_decision(clients, title)

    async def _get_quality_config(service: str | None = None) -> list[dict]:
        """Quality profiles (non-zero custom format scores), custom format names, release
        profiles, and Profilarr sync state. Use this instead of reading arr databases or
        config files over SSH."""
        return await get_quality_config(clients, service)

    async def _get_history(service: str | None = None, limit: int = 30) -> list[dict]:
        """Recent grab, import, and failure events for arr instances, newest first. Use this
        instead of querying arr databases over SSH. Returns at most `limit` events per
        instance (max 80); `truncated` and `total` show when more exist."""
        return await get_history(clients, service, limit)

    async def _get_wanted(service: str | None = None, limit: int = 50) -> list[dict]:
        """Missing and cutoff-unmet items for arr instances, with the reason for each. Use
        this instead of curling arr wanted lists over SSH. Returns at most `limit` items per
        instance (max 200); `truncated` and `total` show when more exist."""
        return await get_wanted(clients, service, limit)

    async def _search_media(term: str, limit: int = 20) -> list[dict]:
        """Find a title in the existing arr libraries: ids, monitored state, path, size on
        disk, file counts. Use this instead of reading arr config files or curling their
        APIs over SSH, and instead of `find` or `du` on the media pool. Returns at most
        `limit` items per instance (max 100); `truncated` and `total` show when more
        exist."""
        return await search_media(clients, term, limit)

    async def _get_indexers() -> list[dict]:
        """Prowlarr indexers (enabled, protocol, priority) and per-indexer query, grab, and
        failure stats. Use this instead of curling Prowlarr over SSH."""
        return await get_indexers(clients)

    async def _get_transcodes(limit: int = 50) -> list[dict]:
        """Tdarr status, nodes, and the staged transcode queue. Use this instead of
        `docker exec` into Tdarr over SSH. Returns at most `limit` staged items;
        `staged_count` gives the full count and `truncated` shows when more exist."""
        return await get_transcodes(clients, limit)

    async def _get_upcoming(service: str | None = None, days: int = 7,
                            limit: int = 100) -> list[dict]:
        """Upcoming episodes, games, and movie releases across arr instances (max 90 days).
        Use this instead of curling arr calendars over SSH. Returns at most `limit` items
        per instance (max 200); `truncated` and `total` show when more exist."""
        return await get_upcoming(clients, service, days, limit)

    async def _get_library(section: str | None = None, term: str | None = None,
                           limit: int = 20) -> list[dict] | dict:
        """Jellyfin libraries (item counts, scan state and progress), scheduled tasks, playback
        sessions with transcode details, and recently added items; `term=` searches series and
        movies by name. `section=` returns one area in full: libraries, recent, sessions or
        tasks. Use this instead of reading `jellyfin.db` for a token and curling Jellyfin over
        SSH. For file paths and sizes, use `search_media`. Lists stop at `limit` (max 100);
        `truncated` and `total` show when more exist."""
        return await get_library(clients, section, term, limit)

    async def _get_cleanup(section: str | None = None, limit: int = 20) -> list[dict] | dict:
        """Cleanuparr state: dry-run mode, cleaner jobs and schedules, seeding rules
        (private/public), unlinked category, stall/slow rules, and strikes (which downloads
        Cleanuparr has flagged, why, and whether they are marked for removal). `section=`
        returns one area in full: config, jobs, rules or strikes. Use this instead of copying
        `cleanuparr.db` or running `docker exec` into Cleanuparr over SSH. Strike lists stop at
        `limit` (max 100); `truncated` and `total` show when more exist."""
        return await get_cleanup(clients, section, limit)

    async def _get_host(section: str | None = None, limit: int = 50) -> list[dict] | dict:
        """Host health from Netdata and TrueNAS: CPU busy and iowait, load, I/O pressure,
        memory (free and available reported separately), swap, ZFS ARC size against its
        max, GPU temperature/power/VRAM, pool capacity/fragmentation/scrub, and TrueNAS
        alerts. `section=` returns datasets (space used), disks (temperatures) or alerts in
        full. Use this instead of running `free`, `uptime`, `nvidia-smi`, `zpool list`,
        `zfs list` or `du` over SSH. Lists stop at `limit` (max 200); `truncated` and
        `total` show when more exist."""
        return await get_host(clients, section, limit)

    async def _get_containers(name: str | None = None, section: str | None = None,
                              lines: int = 50, since: str | None = None,
                              match: str | None = None, limit: int = 100) -> list[dict] | dict:
        """Docker containers on the host: state, health, restart count, exit code (for
        stopped containers), last stop time, image and published ports, with problems
        (unhealthy, restarting, dead, OOM-killed, non-zero exit) listed first. `name=`
        returns one container with its last health-check output, restart policy and
        network (e.g. qbittorrent runs in gluetun's network). `section="logs"` with `name=`
        returns the last `lines` log lines (max 200), optionally `since=` ("15m", "2h",
        "1d" or an ISO time) and `match=` (case-insensitive text filter over the last 2000
        lines). Use this instead of `docker ps`, `docker inspect` or `docker logs` over
        SSH. Lists stop at `limit` (max 200); `truncated` and `total` show when more
        exist."""
        return await get_containers(clients, name, section, lines, since, match, limit)

    async def _get_jobs(service: str | None = None, section: str | None = None,
                        include_routine: bool = False, limit: int = 50) -> list[dict] | dict:
        """What the arrs and Jellyfin are doing: running and queued commands with
        progress (rename, refresh, search) and the series or movies they act on, failed
        commands, recently finished ones (routine housekeeping hidden unless
        `include_routine`), and Jellyfin's running or failed tasks such as a library scan.
        `section="schedule"` lists each arr's scheduled tasks with last and next run. The
        arr keeps finished commands for a few minutes only. Use this instead of the arr's
        System > Tasks page or checking progress over SSH. Lists stop at `limit` (max 50);
        `truncated` and `total` show when more exist."""
        return await get_jobs(clients, service, section, include_routine, limit)

    async def _start_job(action: str | None = None, service: str | None = None,
                         target: str | None = None, season: int | None = None, library: str | None = None,
                         plan_id: str | None = None) -> dict:
        """Start an arr job or a Jellyfin scan, in two steps. First call without plan_id:
        returns a preview of exactly what would happen and a plan_id (valid 10 minutes).
        Then call again with only that plan_id to run it once. action is refresh, rescan,
        search (season= for one Sonarr season), rename (shows the arr's rename preview)
        on one series or movie (service= the arr instance, target= a title or "id:<n>"),
        or scan (service= Jellyfin, library= optional). Follow progress with get_jobs.
        Use this instead of the arr or Jellyfin UI, or curl/rm over SSH."""
        return await start_job(clients, plans, writable, action, service, target, season,
                               library, plan_id)

    register("stack_health", _stack_health)
    register("get_queues", _get_queues)
    register("diagnose", _diagnose)
    register("explain_decision", _explain_decision)
    register("get_quality_config", _get_quality_config)
    register("get_history", _get_history)
    register("get_wanted", _get_wanted)
    register("search_media", _search_media)
    register("get_indexers", _get_indexers)
    register("get_transcodes", _get_transcodes)
    register("get_upcoming", _get_upcoming)
    register("get_library", _get_library)
    register("get_cleanup", _get_cleanup)
    register("get_host", _get_host)
    register("get_containers", _get_containers)
    register("get_jobs", _get_jobs)
    register("start_job", _start_job)
    return mcp
