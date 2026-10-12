from oraclarr_mcp.config import Config, Instance, ServerSettings, Defaults
from oraclarr_mcp.server import build_server, TOOL_SPECS
from oraclarr_mcp.guards import enabled_for_toolsets


def _registered_tool_names(mcp) -> list[str]:
    """Return names of tools registered on the FastMCP instance.

    Uses the synchronous internal tool manager dict, which is always
    available without an event loop in the installed mcp version.
    """
    return list(mcp._tool_manager._tools.keys())


def test_tool_specs_cover_all_fourteen_tools():
    names = {s.name for s in TOOL_SPECS}
    assert names == {
        "stack_health", "get_queues", "diagnose", "explain_decision",
        "get_quality_config", "get_history", "get_wanted", "search_media",
        "get_indexers", "get_transcodes", "get_upcoming", "get_library", "get_cleanup",
        "get_host",
    }


def test_get_upcoming_is_gated_by_the_media_toolset():
    assert "get_upcoming" not in enabled_for_toolsets(TOOL_SPECS, ["downloads"])
    assert "get_upcoming" in enabled_for_toolsets(TOOL_SPECS, ["media"])


def test_all_tool_specs_are_read_risk():
    assert all(s.risk == "read" for s in TOOL_SPECS)


def test_toolset_filter_drops_transcode_when_disabled():
    enabled = enabled_for_toolsets(TOOL_SPECS, ["media"])
    assert "get_transcodes" not in enabled
    assert "stack_health" in enabled  # always


def test_build_server_registers_only_enabled_tools():
    cfg = Config(server=ServerSettings(toolsets=["media"]), defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    mcp = build_server(cfg, clients={})
    registered = set(_registered_tool_names(mcp))
    assert "get_transcodes" not in registered
    assert "stack_health" in registered


def test_build_server_passes_host_and_port_to_fastmcp():
    cfg = Config(server=ServerSettings(toolsets=["media"]), defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    mcp = build_server(cfg, clients={}, host="0.0.0.0", port=7979)
    assert mcp.settings.host == "0.0.0.0"
    assert mcp.settings.port == 7979


def test_build_server_defaults_to_localhost_7979():
    cfg = Config(server=ServerSettings(toolsets=["media"]), defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    mcp = build_server(cfg, clients={})
    assert mcp.settings.host == "127.0.0.1"
    assert mcp.settings.port == 7979


import asyncio  # noqa: E402
import json  # noqa: E402


class _SlowArr:
    name = "sonarr"
    type = "sonarr"

    def __init__(self, delay):
        self._delay = delay

    async def system_status(self):
        await asyncio.sleep(self._delay)
        return {"version": "4.0"}

    async def health(self):
        return []

    async def diskspace(self):
        return []


def _payloads(out) -> list:
    blocks = out[0] if isinstance(out, tuple) else out
    parsed = [json.loads(b.text) for b in blocks]
    if len(parsed) == 1 and isinstance(parsed[0], list):
        return parsed[0]
    return parsed


def _cfg(**server):
    return Config(server=ServerSettings(toolsets=["media"], **server), defaults=Defaults(),
                  instances={"sonarr": Instance(type="sonarr", url="http://h:8989",
                                                api_key="SONARRKEY123")})


async def test_registered_tool_reports_instance_timeout_within_budget():
    mcp = build_server(_cfg(tool_budget_seconds=0.1), clients={"sonarr": _SlowArr(1.0)})
    payloads = _payloads(await mcp.call_tool("stack_health", {}))
    assert payloads[0]["status"] == "timeout"
    assert payloads[0]["error"] == "upstream_timeout"


async def test_registered_tool_can_return_error_object():
    # A list[dict] output schema would reject this dict; the wrapper's Any return allows it.
    mcp = build_server(_cfg(max_output_bytes=10), clients={"sonarr": _SlowArr(0)})
    payloads = _payloads(await mcp.call_tool("stack_health", {}))
    assert payloads[0]["error"] == "output_too_large"


def _params(mcp, tool):
    return mcp._tool_manager._tools[tool].parameters["properties"]


def test_get_queues_exposes_limit():
    cfg = Config(server=ServerSettings(toolsets=["downloads"]), defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    assert _params(build_server(cfg, clients={}), "get_queues")["limit"]["default"] == 100


def test_media_tools_expose_limits():
    cfg = Config(server=ServerSettings(toolsets=["media"]), defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    mcp = build_server(cfg, clients={})
    assert _params(mcp, "search_media")["limit"]["default"] == 20
    assert _params(mcp, "get_wanted")["limit"]["default"] == 50
    assert _params(mcp, "get_history")["limit"]["default"] == 30


def test_transcode_and_upcoming_expose_limits():
    cfg = Config(server=ServerSettings(toolsets=["media", "transcode"]), defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    mcp = build_server(cfg, clients={})
    assert _params(mcp, "get_transcodes")["limit"]["default"] == 50
    assert _params(mcp, "get_upcoming")["limit"]["default"] == 100


BOUNDED_TOOLS = {"get_queues", "diagnose", "explain_decision", "get_history", "get_wanted",
                 "search_media", "get_upcoming", "get_transcodes", "get_library",
                 "get_cleanup", "get_host"}


def test_every_tool_description_says_when_to_use_it_instead_of_ssh():
    cfg = Config(server=ServerSettings(toolsets=["media", "downloads", "transcode", "library",
                                                 "host"]),
                 defaults=Defaults(),
                 instances={"sonarr": Instance(type="sonarr", url="http://h:8989", api_key="K")})
    tools = build_server(cfg, clients={})._tool_manager._tools
    assert set(tools) == {s.name for s in TOOL_SPECS}
    for name, tool in tools.items():
        assert "instead of" in tool.description and "SSH" in tool.description, name
        if name in BOUNDED_TOOLS:
            assert "truncated" in tool.description, name


def test_get_library_registers_only_with_library_toolset():
    base = dict(defaults=Defaults(),
                instances={"jellyfin": Instance(type="jellyfin", url="http://h:8096",
                                                api_key="K")})
    without = build_server(Config(server=ServerSettings(toolsets=["media"]), **base), clients={})
    with_lib = build_server(Config(server=ServerSettings(toolsets=["library"]), **base),
                            clients={})
    assert "get_library" not in _registered_tool_names(without)
    assert "get_library" in _registered_tool_names(with_lib)
    assert _params(with_lib, "get_library")["limit"]["default"] == 20


def test_get_cleanup_registers_with_downloads_toolset():
    cfg = Config(server=ServerSettings(toolsets=["downloads"]), defaults=Defaults(),
                 instances={"cleanuparr": Instance(type="cleanuparr", url="http://h:11011",
                                                   api_key="K")})
    mcp = build_server(cfg, clients={})
    assert "get_cleanup" in _registered_tool_names(mcp)
    assert _params(mcp, "get_cleanup")["limit"]["default"] == 20


def test_get_host_registers_with_host_toolset():
    cfg = Config(server=ServerSettings(toolsets=["host"]), defaults=Defaults(),
                 instances={"netdata": Instance(type="netdata", url="http://h:20999")})
    mcp = build_server(cfg, clients={})
    assert "get_host" in _registered_tool_names(mcp)
    assert _params(mcp, "get_host")["limit"]["default"] == 50
