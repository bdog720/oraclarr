from mcp.server.fastmcp import FastMCP
from .config import Config
from .clients.base import BaseClient
from .guards import tool_spec, enabled_for_toolsets, ensure_allowed, ToolSpec
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

    def register(name: str, fn):
        if name not in enabled:
            return
        ensure_allowed(spec_by_name[name], cfg.server.allow_writes)
        mcp.tool(name=name)(fn)

    async def _stack_health() -> list[dict]:
        """Health/status of every configured service: versions, warnings, disk, nodes."""
        return await stack_health(clients)

    async def _get_queues(service: str | None = None) -> dict:
        """Unified active download queue (arr queue cross-referenced with qBittorrent)."""
        return await get_queues(clients, service)

    async def _diagnose(title: str) -> dict:
        """Trace one title through the arr->download->transcode pipeline."""
        return await diagnose(clients, title)

    async def _explain_decision(title: str) -> dict:
        """Explain why a title was grabbed or is being upgraded (profile, custom formats, grab history)."""
        return await explain_decision(clients, title)

    async def _get_quality_config(service: str | None = None) -> list[dict]:
        """Quality profiles, custom formats, release profiles, and Profilarr sync state."""
        return await get_quality_config(clients, service)

    async def _get_history(service: str | None = None, limit: int = 30) -> list[dict]:
        """Recent grab/import/failure history for an arr service."""
        return await get_history(clients, service, limit)

    async def _get_wanted(service: str | None = None) -> list[dict]:
        """Missing and cutoff-unmet items for an arr service."""
        return await get_wanted(clients, service)

    async def _search_media(term: str) -> list[dict]:
        """Find a title in the existing arr library and report its status."""
        return await search_media(clients, term)

    async def _get_indexers() -> list[dict]:
        """Prowlarr indexer health and stats."""
        return await get_indexers(clients)

    async def _get_transcodes() -> list[dict]:
        """Tdarr transcode queue and node health."""
        return await get_transcodes(clients)

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
    return mcp
