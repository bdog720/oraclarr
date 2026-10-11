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
    async def staged(self): return [{"_id": "a.mkv"}]

async def test_get_indexers():
    res = await get_indexers({"prowlarr": FakeProwlarr()})
    assert res[0]["data"]["indexers"][0]["name"] == "nyaa"

async def test_get_transcodes():
    res = await get_transcodes({"tdarr": FakeTdarr()})
    d = res[0]["data"]
    assert d["staged"][0]["file"] == "a.mkv" and "n1" in d["nodes"]


class RichProwlarr(FakeProwlarr):
    async def indexers(self):
        return [{"name": "nyaa", "enable": True, "protocol": "torrent", "priority": 25,
                 "fields": [{"name": "baseUrl", "value": "https://x"}], "capabilities": {}}]
    async def indexer_stats(self):
        return {"indexers": [{"indexerName": "nyaa", "numberOfQueries": 10,
                              "numberOfGrabs": 2, "numberOfFailedQueries": 1,
                              "numberOfFailedGrabs": 0, "averageResponseTime": 350,
                              "indexerId": 4}]}


async def test_get_indexers_projects_fields():
    d = (await get_indexers({"prowlarr": RichProwlarr()}))[0]["data"]
    assert d["indexers"] == [{"name": "nyaa", "enabled": True, "protocol": "torrent",
                              "priority": 25}]
    assert d["stats"] == [{"name": "nyaa", "queries": 10, "grabs": 2, "failed_queries": 1,
                           "failed_grabs": 0, "avg_response_ms": 350}]


class BigTdarr(FakeTdarr):
    async def staged(self):
        return [{"_id": f"{i}.mkv"} for i in range(5)]


async def test_get_transcodes_bounds_staged():
    row = (await get_transcodes({"tdarr": BigTdarr()}, limit=2))[0]
    assert row["data"]["staged_count"] == 5
    assert [s["file"] for s in row["data"]["staged"]] == ["0.mkv", "1.mkv"]
    assert row["total"] == 5 and row["truncated"] is True


class LiveShapeTdarr(FakeTdarr):
    async def staged(self):
        return [{"_id": "/media/tv/Show/S01E01.mkv", "status": "processing",
                 "workerType": "transcodegpu", "nodeID": "node1", "start": 1791756922182,
                 "inLimbo": False, "workDir": "/transcode/x",
                 "flowPluginHandler": {"blob": "x" * 50_000},
                 "originalLibraryFile": {"ffProbeData": {"streams": ["y" * 1_000]}}}]


async def test_get_transcodes_projects_staged_items():
    row = (await get_transcodes({"tdarr": LiveShapeTdarr()}))[0]
    assert row["data"]["staged"] == [{"file": "/media/tv/Show/S01E01.mkv",
                                      "status": "processing", "worker_type": "transcodegpu",
                                      "node": "node1", "started": 1791756922182}]


async def test_get_transcodes_projects_live_staged_fixture():
    import json
    from pathlib import Path
    live = json.loads((Path(__file__).parent.parent / "fixtures" / "tdarr_staged.json")
                      .read_text(encoding="utf-8"))

    class LiveTdarr(FakeTdarr):
        async def staged(self):
            return live

    rows = (await get_transcodes({"tdarr": LiveTdarr()}))[0]["data"]["staged"]
    assert len(rows) == len(live)
    for row in rows:
        assert set(row) == {"file", "status", "worker_type", "node", "started"}
        assert row["file"].endswith(".mkv")
        assert row["status"] and row["worker_type"] and row["node"]
        assert isinstance(row["started"], int)
