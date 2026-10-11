from oraclarr_mcp.tools.queues import get_queues

class FakeArr:
    name="sonarr"; type="sonarr"
    async def queue(self):
        return [{"title": "Show.S03E04", "downloadId": "H1", "status": "downloading",
                 "trackedDownloadState": "downloading", "size": 1000, "sizeleft": 400}]
    async def queue_page(self, limit):
        recs = await self.queue()
        return recs[:limit], len(recs)

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


import asyncio  # noqa: E402
import time  # noqa: E402


class ManyArr(FakeArr):
    async def queue(self):
        return [{"title": f"Ep {i}", "downloadId": f"H{i}", "size": 10, "sizeleft": 5}
                for i in range(3)]


async def test_queue_limit_truncates_and_reports_total():
    res = await get_queues({"sonarr": ManyArr()}, limit=2)
    assert len(res["items"]) == 2
    assert res["total"] == 3
    assert res["truncated"] is True


class SlowArr(FakeArr):
    async def queue(self):
        await asyncio.sleep(0.3)
        return await super().queue()


class SlowQbit(FakeQbit):
    async def torrents(self):
        await asyncio.sleep(0.3)
        return await super().torrents()


async def test_queue_fetches_qbit_and_arr_in_parallel():
    t0 = time.monotonic()
    res = await get_queues({"sonarr": SlowArr(), "qbit": SlowQbit()})
    assert time.monotonic() - t0 < 0.5
    assert res["items"][0]["qbit"]["state"] == "stalledDL"


async def test_queue_reports_failing_arr_in_errors():
    class Dead(FakeArr):
        async def queue(self):
            raise RuntimeError("down")
    res = await get_queues({"sonarr": Dead(), "qbit": FakeQbit()})
    assert res["items"] == []
    assert res["errors"][0]["instance"] == "sonarr"


class PagedArr(FakeArr):
    async def queue_page(self, limit):
        rec = (await self.queue())[0]
        return [rec, rec], 300  # upstream holds more than one page


async def test_queue_total_comes_from_upstream_total_records():
    res = await get_queues({"sonarr": PagedArr()}, limit=500)
    assert len(res["items"]) == 2
    assert res["total"] == 300
    assert res["truncated"] is True


async def test_queue_tolerates_torrent_with_null_state():
    class NullState(FakeQbit):
        async def torrents(self):
            return [{"hash": "h1", "state": None, "progress": 0.1}]
    res = await get_queues({"sonarr": FakeArr(), "qbit": NullState()})
    assert res["items"][0]["stalled"] is False
