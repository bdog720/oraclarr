"""A new arr-family type must reach every selector at once.

A missed selector drops the instance silently instead of raising, so these
tests assert all four together.
"""
from oraclarr_mcp.tools._arr import arr_clients, media_kind
from oraclarr_mcp.tools.queues import get_queues
from oraclarr_mcp.tools.quality_config import get_quality_config
from oraclarr_mcp.tools.health import stack_health


class FakeSportarr:
    name = "sportarr"; type = "sportarr"
    async def system_status(self): return {"version": "4.1.6"}
    async def health(self): return [{"message": "warn"}]
    async def diskspace(self): return [{"path": "/data", "freeSpace": 1}]
    async def queue(self): return [{"title": "Spurs vs Hawks", "downloadId": "H1",
                                    "trackedDownloadState": "downloading",
                                    "size": 100, "sizeleft": 25}]
    async def queue_page(self, limit):
        recs = await self.queue()
        return recs[:limit], len(recs)
    async def quality_profiles(self): return [{"id": 1, "name": "WEB-1080p"}]
    async def custom_formats(self): return [{"id": 1, "name": "BR-DISK"}]
    async def release_profiles(self): return []


def _clients(): return {"sportarr": FakeSportarr()}


def test_arr_clients_includes_sportarr():
    assert "sportarr" in arr_clients(_clients(), None)


def test_media_kind_for_sportarr_is_series():
    assert media_kind(FakeSportarr()) == "series"


async def test_get_queues_includes_sportarr():
    res = await get_queues(_clients())
    assert res["items"][0]["instance"] == "sportarr"
    assert res["items"][0]["percent"] == 75.0


async def test_get_quality_config_includes_sportarr():
    res = await get_quality_config(_clients())
    assert res[0]["status"] == "ok"
    assert res[0]["data"]["profiles"][0]["name"] == "WEB-1080p"


async def test_stack_health_summarises_sportarr_like_an_arr():
    res = await stack_health(_clients())
    assert res[0]["status"] == "ok"
    assert res[0]["data"]["version"] == "4.1.6"
    assert res[0]["data"]["warnings"] == ["warn"]


async def test_get_jobs_includes_sportarr_with_a_note():
    from oraclarr_mcp.tools.jobs import get_jobs
    res = await get_jobs(_clients())
    assert res[0]["instance"] == "sportarr" and "not_supported" in res[0]["data"]
