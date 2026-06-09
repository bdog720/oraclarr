from oraclarr_mcp.tools.history import get_history
from oraclarr_mcp.tools.wanted import get_wanted
from oraclarr_mcp.tools.search import search_media

class FakeArr:
    name="sonarr"; type="sonarr"
    async def history(self, limit=30): return [{"eventType": "grabbed", "sourceTitle": "X"}]
    async def wanted_missing(self): return [{"title": "Missing S01E01"}]
    async def wanted_cutoff(self): return [{"title": "Upgrade S01E02"}]
    async def lookup_library(self, term, media): return [{"title": f"{term} match"}]

def _clients(): return {"sonarr": FakeArr()}

async def test_get_history_filters_to_one_service():
    res = await get_history(_clients(), service="sonarr", limit=5)
    assert res[0]["status"] == "ok"
    assert res[0]["data"][0]["eventType"] == "grabbed"

async def test_get_history_unknown_service_returns_empty():
    assert await get_history(_clients(), service="nope", limit=5) == []

async def test_get_wanted_merges_missing_and_cutoff():
    res = await get_wanted(_clients(), service="sonarr")
    titles = [w["title"] for w in res[0]["data"]]
    assert "Missing S01E01" in titles and "Upgrade S01E02" in titles

async def test_search_media_uses_series_for_sonarr():
    res = await search_media(_clients(), term="Foo")
    assert res[0]["data"][0]["title"] == "Foo match"
