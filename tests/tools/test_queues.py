from oraclarr_mcp.tools.queues import get_queues

class FakeArr:
    name="sonarr"; type="sonarr"
    async def queue(self):
        return [{"title": "Show.S03E04", "downloadId": "H1", "status": "downloading",
                 "trackedDownloadState": "downloading", "size": 1000, "sizeleft": 400}]

class FakeQbit:
    name="qbit"; type="qbittorrent"
    async def torrents(self):
        return [{"hash": "h1", "name": "Show.S03E04", "state": "stalledDL", "progress": 0.6}]

async def test_queue_joins_arr_to_qbit_by_download_id():
    res = await get_queues({"sonarr": FakeArr(), "qbit": FakeQbit()})
    rows = res["items"]
    item = rows[0]
    assert item["title"] == "Show.S03E04"
    assert item["qbit"]["state"] == "stalledDL"   # matched H1 -> h1 (case-insensitive)
    assert item["stalled"] is True

async def test_queue_with_no_qbit_match_marks_unmatched():
    class Other(FakeQbit):
        async def torrents(self): return []
    res = await get_queues({"sonarr": FakeArr(), "qbit": Other()})
    assert res["items"][0]["qbit"] is None
