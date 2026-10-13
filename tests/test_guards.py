from oraclarr_mcp.config import Config, Instance, ServerSettings
from oraclarr_mcp.guards import (ToolSpec, enabled_for_toolsets, tool_spec, writable_instances,
                                 writes_enabled)

def test_tool_spec_records_tags():
    spec = tool_spec(name="get_wanted", risk="read", domain="media")
    assert isinstance(spec, ToolSpec)
    assert spec.risk == "read" and spec.domain == "media"

def test_enabled_for_toolsets_filters_by_domain():
    specs = [tool_spec("a", "read", "media"), tool_spec("b", "read", "transcode")]
    names = enabled_for_toolsets(specs, ["media"])
    assert names == ["a"]

def test_health_domain_always_enabled():
    specs = [tool_spec("stack_health", "read", "always")]
    assert enabled_for_toolsets(specs, ["transcode"]) == ["stack_health"]


def _cfg(server_writes, inst_writes, enabled=True):
    return Config(server=ServerSettings(allow_writes=server_writes),
                  instances={"sonarr": Instance(type="sonarr", url="http://h", api_key="K",
                                                allow_writes=inst_writes, enabled=enabled)})


def test_writes_need_both_switches_and_an_enabled_instance():
    assert writes_enabled(_cfg(True, True)) is True
    assert writes_enabled(_cfg(True, False)) is False
    assert writes_enabled(_cfg(False, True)) is False
    assert writes_enabled(_cfg(True, True, enabled=False)) is False


def test_writable_instances():
    assert writable_instances(_cfg(True, True)) == {"sonarr"}
    assert writable_instances(_cfg(False, True)) == set()
