import json
from pathlib import Path

import httpx
import respx

from oraclarr_mcp.clients.base import NoAuth
from oraclarr_mcp.clients.netdata import CACHE_TTL_S, NetdataClient

FX = Path(__file__).parent.parent / "fixtures"
B = "http://h"


def _fx(name):
    return json.loads((FX / f"netdata_{name}.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _client(clock=None):
    return NetdataClient("netdata", "netdata", B, NoAuth(), timeout=5, clock=clock or Clock())


@respx.mock
async def test_latest_parses_dimensions_and_sends_v2_params():
    route = respx.get(f"{B}/api/v2/data").mock(
        return_value=httpx.Response(200, json=_fx("system_ram")))
    c = _client()
    ram = await c.latest("system.ram")
    p = route.calls.last.request.url.params
    assert p["contexts"] == "system.ram" and p["scope_contexts"] == "system.ram"
    assert p["after"] == "-10" and p["points"] == "1" and p["format"] == "json2"
    assert p["group_by"] == "instance,dimension" and p["time_group"] == "average"
    assert set(ram) == {"free", "used", "cached", "buffers"}
    assert all(isinstance(v, (int, float)) for v in ram.values())
    await c.aclose()


@respx.mock
async def test_cpu_has_iowait_and_arc_has_max():
    respx.get(f"{B}/api/v2/data", params={"contexts": "system.cpu"}).mock(
        return_value=httpx.Response(200, json=_fx("system_cpu")))
    respx.get(f"{B}/api/v2/data", params={"contexts": "zfs.arc_size"}).mock(
        return_value=httpx.Response(200, json=_fx("zfs_arc_size")))
    c = _client()
    assert "iowait" in await c.latest("system.cpu")
    assert "max (high water)" in await c.latest("zfs.arc_size")
    await c.aclose()


@respx.mock
async def test_latest_by_instance_returns_one_dict_per_gpu():
    respx.get(f"{B}/api/v2/data").mock(
        return_value=httpx.Response(200, json=_fx("nvidia_smi_gpu_frame_buffer_memory_usage")))
    c = _client()
    gpus = await c.latest_by_instance("nvidia_smi.gpu_frame_buffer_memory_usage")
    assert len(gpus) >= 1 and {"free", "used"} <= set(gpus[0])
    await c.aclose()


@respx.mock
async def test_missing_context_is_empty():
    respx.get(f"{B}/api/v2/data").mock(
        return_value=httpx.Response(200, json=_fx("missing_context")))
    c = _client()
    assert await c.latest("nvidia_smi.no_such_context") == {}
    assert await c.latest_by_instance("nvidia_smi.no_such_context") == []
    await c.aclose()


@respx.mock
async def test_netdata_cache_ttl():
    route = respx.get(f"{B}/api/v2/data").mock(
        return_value=httpx.Response(200, json=_fx("system_load")))
    clock = Clock()
    c = _client(clock)
    await c.latest("system.load")
    await c.latest("system.load")
    assert route.call_count == 1
    clock.t += CACHE_TTL_S + 1
    await c.latest("system.load")
    assert route.call_count == 2
    await c.aclose()


@respx.mock
async def test_info():
    respx.get(f"{B}/api/v1/info").mock(return_value=httpx.Response(200, json=_fx("info")))
    c = _client()
    assert (await c.info())["version"]
    await c.aclose()


@respx.mock
async def test_null_values_are_dropped():
    respx.get(f"{B}/api/v2/data").mock(return_value=httpx.Response(200, json={"result": {
        "labels": ["time", "free,system.ram@n", "used,system.ram@n"],
        "data": [[1, [None, 0, 0], [5.0, 0, 0]]]}}))
    c = _client()
    assert await c.latest("system.ram") == {"used": 5.0}
    await c.aclose()
