from oraclarr_mcp.tools.indexers import get_indexers
from oraclarr_mcp.tools.transcodes import get_transcodes

class FakeProwlarr:
    name="prowlarr"; type="prowlarr"
    async def indexers(self): return [{"name": "nyaa", "enable": True}]
    async def indexer_stats(self): return {"indexers": []}

class FakeTdarr:
    name="tdarr"; type="tdarr"
    async def status(self): return {"status": "ok"}
    async def nodes(self): return {"n1": {"nodeName": "n1"}}
    async def staged(self): return [{"file": "a.mkv"}]

async def test_get_indexers():
    res = await get_indexers({"prowlarr": FakeProwlarr()})
    assert res[0]["data"]["indexers"][0]["name"] == "nyaa"

async def test_get_transcodes():
    res = await get_transcodes({"tdarr": FakeTdarr()})
    d = res[0]["data"]
    assert d["staged"][0]["file"] == "a.mkv" and "n1" in d["nodes"]
