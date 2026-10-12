from oraclarr_mcp.models import InstanceResult, MediaRef

def test_instance_result_ok_defaults():
    r = InstanceResult(instance="sonarr", type="sonarr", status="ok", data={"a": 1})
    assert r.error is None and r.data == {"a": 1}

def test_instance_result_serializes_status():
    r = InstanceResult(instance="qbit", type="qbittorrent", status="unreachable", error="timeout")
    assert r.model_dump()["status"] == "unreachable"

def test_media_ref_carries_external_ids():
    m = MediaRef(title="Foo", instance="sonarr", item_id=12, tvdb_id=999)
    assert m.tvdb_id == 999 and m.tmdb_id is None and m.imdb_id is None


def test_arr_types_lists_every_arr_family_type():
    from oraclarr_mcp.models import ARR_TYPES
    assert ARR_TYPES == ("sonarr", "radarr", "sportarr")


def test_instance_result_new_fields_default_empty():
    r = InstanceResult(instance="a", type="sonarr", status="ok")
    assert r.after_s is None
    assert r.total is None
    assert r.truncated is False


def test_instance_result_accepts_timeout_status_and_fields():
    r = InstanceResult(instance="a", type="sonarr", status="timeout",
                       error="upstream_timeout", after_s=1.5, total=3, truncated=True)
    d = r.model_dump()
    assert d["status"] == "timeout"
    assert d["after_s"] == 1.5
    assert d["total"] == 3
    assert d["truncated"] is True


def test_domain_includes_containers():
    from typing import get_args
    from oraclarr_mcp.models import Domain
    assert "containers" in get_args(Domain)
