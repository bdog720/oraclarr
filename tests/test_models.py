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
