from mcp.server.fastmcp import FastMCP
from .config import Config
from .clients.base import BaseClient
from .guards import tool_spec, enabled_for_toolsets, ensure_allowed, ToolSpec
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

    def register(name: str, fn):
        if name not in enabled:
            return
        ensure_allowed(spec_by_name[name], cfg.server.allow_writes)
        mcp.tool(name=name)(guarded(
            name, fn,
            budget_s=cfg.server.tool_budget_seconds,
            max_bytes=cfg.server.max_output_bytes,
            redactor=redactor,
        ))

    async def _stack_health() -> list[dict]:
        """Health and status of every configured service: versions, warnings, disk space,
        Tdarr nodes. Use this instead of `docker ps` or curling service APIs over SSH to
        check whether a service is up."""
        return await stack_health(clients)

    async def _get_queues(service: str | None = None, limit: int = 100) -> dict:
        """Unified active download queue: arr queues joined to qBittorrent torrents
        (progress, stalled). Use this instead of curling Sonarr/Radarr/qBittorrent over
        SSH. Returns at most `limit` items; `truncated` and `total` show when more exist."""
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
    return mcp
