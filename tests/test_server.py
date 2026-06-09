from oraclarr_mcp.config import Config, Instance, ServerSettings, Defaults
from oraclarr_mcp.server import build_server, TOOL_SPECS
from oraclarr_mcp.guards import enabled_for_toolsets


def _registered_tool_names(mcp) -> list[str]:
    """Return names of tools registered on the FastMCP instance.

    Uses the synchronous internal tool manager dict, which is always
    available without an event loop in the installed mcp version.
    """
    return list(mcp._tool_manager._tools.keys())


def test_tool_specs_cover_all_ten_tools():
    names = {s.name for s in TOOL_SPECS}
    assert names == {
        "stack_health", "get_queues", "diagnose", "explain_decision",
        "get_quality_config", "get_history", "get_wanted", "search_media",
        "get_indexers", "get_transcodes",
    }


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
