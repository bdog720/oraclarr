from oraclarr_mcp.config import Config, Instance, ServerSettings, Defaults
from oraclarr_mcp.server import build_server, TOOL_SPECS
from oraclarr_mcp.guards import enabled_for_toolsets


def _registered_tool_names(mcp) -> list[str]:
    """Return names of tools registered on the FastMCP instance.

    Uses the synchronous internal tool manager dict, which is always
    available without an event loop in the installed mcp version.
    """
    return list(mcp._tool_manager._tools.keys())


def test_tool_specs_cover_all_eleven_tools():
    names = {s.name for s in TOOL_SPECS}
    assert names == {
        "stack_health", "get_queues", "diagnose", "explain_decision",
        "get_quality_config", "get_history", "get_wanted", "search_media",
        "get_indexers", "get_transcodes", "get_upcoming",
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
