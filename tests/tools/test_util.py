import asyncio
import time
from types import SimpleNamespace

import httpx

from oraclarr_mcp.budget import set_deadline, reset_deadline
from oraclarr_mcp.models import InstanceResult
from oraclarr_mcp.tools._util import (
    Bounded, bounded, clamp, fan_out, merge_matches, probe,
)


class Fake:
    def __init__(self, name, delay=0.0, result="ok-data"):
        self.name = name
        self.type = "sonarr"
        self.delay = delay
        self.result = result

    async def work(self):
        await asyncio.sleep(self.delay)
        return self.result


async def test_probe_without_deadline_behaves_as_before():
    r = await probe(Fake("a", 0.05), lambda c: c.work())
    assert r.status == "ok" and r.data == "ok-data"


async def test_slow_instance_times_out_and_fast_peer_returns():
    token = set_deadline(0.2)
    try:
        t0 = time.monotonic()
        res = await fan_out({"slow": Fake("slow", 1.0), "fast": Fake("fast")},
                            lambda c: c.work())
        elapsed = time.monotonic() - t0
    finally:
        reset_deadline(token)
    by = {r["instance"]: r for r in res}
    assert by["slow"]["status"] == "timeout"
    assert by["slow"]["error"] == "upstream_timeout"
    assert by["slow"]["after_s"] >= 0.15
    assert by["fast"]["status"] == "ok" and by["fast"]["data"] == "ok-data"
    assert elapsed < 0.5


async def test_expired_deadline_returns_timeout_without_calling():
    called = []

    async def fn(c):
        called.append(1)
        return 1

    token = set_deadline(-1)
    try:
        r = await probe(Fake("a"), fn)
    finally:
        reset_deadline(token)
    assert r.status == "timeout"
    assert r.error == "upstream_timeout"
    assert called == []


async def test_httpx_read_timeout_reports_client_timeout():
    c = Fake("a")
    c._http = SimpleNamespace(timeout=httpx.Timeout(10))

    async def fn(_):
        raise httpx.ReadTimeout("read timed out")

    r = await probe(c, fn)
    assert r.status == "timeout"
    assert r.after_s == 10.0


async def test_probe_unpacks_bounded():
    async def fn(_):
        return bounded([1, 2, 3], 2)

    r = await probe(Fake("a"), fn)
    assert r.data == [1, 2]
    assert r.total == 3
    assert r.truncated is True


def test_bounded_defaults_total_to_item_count():
    b = bounded([1, 2], 5)
    assert b == Bounded(data=[1, 2], total=2, truncated=False)


def test_bounded_uses_upstream_total():
    b = bounded([1, 2], 2, total=40)
    assert b.total == 40 and b.truncated is True


def test_bounded_total_never_below_item_count():
    b = bounded([1, 2, 3], 2, total=0)  # upstream omitted totalRecords
    assert b.total == 3
    assert b.data == [1, 2]
    assert b.truncated is True


def test_clamp_bounds():
    assert clamp(0, 200) == 1
    assert clamp(-5, 200) == 1
    assert clamp(10_000, 200) == 200
    assert clamp(30, 200) == 30


def test_merge_matches_flattens_ok_and_lists_errors():
    ok = InstanceResult(instance="a", type="sonarr", status="ok",
                        data=[{"title": "X"}], total=25, truncated=True)
    bad = InstanceResult(instance="b", type="radarr", status="timeout",
                         error="upstream_timeout", after_s=1.0)
    out = merge_matches("X", [ok, bad])
    assert out["query"] == "X"
    assert out["matches"] == [{"title": "X"}]
    assert out["truncated"] is True
    assert out["errors"][0]["instance"] == "b"
    assert out["errors"][0]["status"] == "timeout"
