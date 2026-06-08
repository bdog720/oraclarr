import pytest
from oraclarr_mcp.guards import tool_spec, enabled_for_toolsets, ToolSpec, WriteNotAllowed, ensure_allowed

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

def test_ensure_allowed_blocks_writes_when_disabled():
    with pytest.raises(WriteNotAllowed):
        ensure_allowed(tool_spec("x", "safe_write", "media"), allow_writes=False)

def test_ensure_allowed_permits_read_always():
    ensure_allowed(tool_spec("x", "read", "media"), allow_writes=False)  # no raise
