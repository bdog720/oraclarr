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


class FakeCl:
    type = "cleanuparr"

    def __init__(self, name="cleanuparr", strikes=None, total=None, fail=False, bad=False):
        self.name = name
        self._strikes = strikes if strikes is not None else []
        self._total = total
        self._fail = fail
        self._bad = bad
        self.page_sizes = []

    async def strikes(self, page_size):
        self.page_sizes.append(page_size)
        if self._fail:
            raise RuntimeError("cleanuparr down")
        if self._bad:
            return ["not-a-dict"], 1
        total = self._total if self._total is not None else len(self._strikes)
        return self._strikes, total


H1_STRIKE = {"downloadId": "H1", "totalStrikes": 4, "strikesByType": {"Stalled": 4},
             "isMarkedForRemoval": True, "hasDryRunStrikes": False}


async def test_queue_shows_cleanuparr_strikes():
    cl = FakeCl(strikes=[H1_STRIKE])
    res = await get_queues({"sonarr": FakeArr(), "qbit": FakeQbit(), "cleanuparr": cl})
    assert res["items"][0]["cleanuparr"] == {"strikes": 4, "by_type": {"Stalled": 4},
                                             "marked_for_removal": True, "dry_run": False}
    assert cl.page_sizes == [500]


async def test_queue_strike_match_is_case_insensitive():
    cl = FakeCl(strikes=[{**H1_STRIKE, "downloadId": "h1"}])
    res = await get_queues({"sonarr": FakeArr(), "cleanuparr": cl})
    assert res["items"][0]["cleanuparr"]["strikes"] == 4


async def test_queue_without_strike_is_zero():
    cl = FakeCl(strikes=[{**H1_STRIKE, "downloadId": "OTHER"}])
    res = await get_queues({"sonarr": FakeArr(), "cleanuparr": cl})
    assert res["items"][0]["cleanuparr"] == {"strikes": 0}


async def test_queue_truncated_strikes_without_match_is_unknown():
    cl = FakeCl(strikes=[{**H1_STRIKE, "downloadId": "OTHER"}], total=900)
    res = await get_queues({"sonarr": FakeArr(), "cleanuparr": cl})
    assert res["items"][0]["cleanuparr"] is None


async def test_queue_cleanuparr_down_gives_null_and_error():
    res = await get_queues({"sonarr": FakeArr(), "cleanuparr": FakeCl(fail=True)})
    assert res["items"][0]["cleanuparr"] is None
    assert res["items"][0]["title"] == "Show.S03E04"
    assert [e["instance"] for e in res["errors"]] == ["cleanuparr"]


async def test_queue_one_cleanuparr_down_uses_the_other():
    up = FakeCl(name="cl-up", strikes=[H1_STRIKE])
    down = FakeCl(name="cl-down", fail=True)
    res = await get_queues({"sonarr": FakeArr(), "cl-up": up, "cl-down": down})
    assert res["items"][0]["cleanuparr"]["strikes"] == 4
    assert [e["instance"] for e in res["errors"]] == ["cl-down"]


async def test_queue_malformed_cleanuparr_reply_fails_only_that_instance():
    res = await get_queues({"sonarr": FakeArr(), "cleanuparr": FakeCl(bad=True)})
    assert res["items"][0]["title"] == "Show.S03E04"
    assert res["items"][0]["cleanuparr"] is None
    assert res["errors"][0]["instance"] == "cleanuparr"


async def test_queue_without_cleanuparr_has_no_key():
    res = await get_queues({"sonarr": FakeArr()})
    assert "cleanuparr" not in res["items"][0]
