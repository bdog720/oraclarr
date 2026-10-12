import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from oraclarr_mcp.clients.base import NoAuth
from oraclarr_mcp.clients.docker import (CACHE_TTL_S, DockerClient, DockerProxyRefused,
                                         DockerRequestFailed, demux, slim_inspect,
                                         slim_listing)

FX = Path(__file__).parent.parent / "fixtures"
B = "http://h"
CANARY = "ENV-CANARY-SECRET"


def _fx(name):
    return json.loads((FX / f"docker_{name}.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _client(clock=None):
    return DockerClient("docker", "docker", B, NoAuth(), timeout=5, clock=clock or Clock())


def _frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


def _dirty_inspect():
    d = _fx("inspect_sonarr")
    d = dict(d, Mounts=[{"Source": "/mnt/" + CANARY}], Args=[CANARY], Path=CANARY,
             NetworkSettings={"IPAddress": CANARY}, GraphDriver={"Data": CANARY})
    d["Config"] = dict(d["Config"], Env=[f"API_KEY={CANARY}"],
                       Labels={**d["Config"]["Labels"], "secret.label": CANARY})
    d["HostConfig"] = dict(d["HostConfig"], Binds=[CANARY])
    return d


def test_demux_splits_stdout_and_stderr_frames():
    raw = _frame(1, b"2026-10-12T06:00:00.1Z one\n") + _frame(2, b"2026-10-12T06:00:01.2Z two\n")
    assert demux(raw, tty=False) == [("stdout", "2026-10-12T06:00:00.1Z one"),
                                     ("stderr", "2026-10-12T06:00:01.2Z two")]


def test_demux_joins_line_split_across_frames():
    raw = _frame(1, b"T half") + _frame(1, b" and rest\nT next\n")
    assert demux(raw, tty=False) == [("stdout", "T half and rest"), ("stdout", "T next")]


def test_demux_strips_carriage_return():
    assert demux(_frame(1, b"T line\r\n"), tty=False) == [("stdout", "T line")]


def test_demux_keeps_truncated_final_frame():
    raw = _frame(1, b"T full\n") + bytes([2, 0, 0, 0, 0, 0, 0, 50]) + b"T cut"
    assert demux(raw, tty=False) == [("stdout", "T full"), ("stderr", "T cut")]


def test_demux_tty_is_plain_text():
    assert demux(b"T a\nT b\n", tty=True) == [("stdout", "T a"), ("stdout", "T b")]


def test_demux_replaces_invalid_utf8():
    assert demux(_frame(1, b"T \xff\n"), tty=False) == [("stdout", "T �")]


def test_slim_inspect_keeps_allowlist_only():
    slim = slim_inspect(_dirty_inspect())
    assert set(slim) == {"Id", "Name", "RestartCount", "State", "Config", "HostConfig"}
    assert set(slim["Config"]) == {"Image", "Tty"}
    assert set(slim["HostConfig"]) == {"NetworkMode", "RestartPolicy"}
    assert CANARY not in json.dumps(slim)


def test_slim_listing_keeps_compose_labels_only():
    row = dict(_fx("containers")[0], Mounts=[{"Source": CANARY}], Command=CANARY)
    row["Labels"] = {**row["Labels"], "other": CANARY}
    slim = slim_listing(row)
    assert set(slim) == {"Id", "Names", "Image", "State", "Status", "Ports", "Labels",
                         "HostConfig"}
    assert set(slim["Labels"]) <= {"com.docker.compose.project", "com.docker.compose.service"}
    assert CANARY not in json.dumps(slim)


@respx.mock
async def test_containers_lists_all_and_caches_for_ttl():
    clock = Clock()
    route = respx.get(f"{B}/containers/json").mock(
        return_value=httpx.Response(200, json=_fx("containers")))
    c = _client(clock)
    first = await c.containers()
    assert route.calls.last.request.url.params["all"] == "1"
    assert len(first) == 24 and first[0]["Names"]
    await c.containers()
    assert route.call_count == 1
    clock.t += CACHE_TTL_S
    await c.containers()
    assert route.call_count == 2


@respx.mock
async def test_inspect_is_slimmed_and_cached():
    d = _dirty_inspect()
    route = respx.get(f"{B}/containers/{d['Id']}/json").mock(
        return_value=httpx.Response(200, json=d))
    c = _client()
    got = await c.inspect(d["Id"])
    await c.inspect(d["Id"])
    assert route.call_count == 1
    assert CANARY not in json.dumps(got) and got["RestartCount"] == d["RestartCount"]


@respx.mock
async def test_inspect_404_returns_none():
    respx.get(f"{B}/containers/gone/json").mock(return_value=httpx.Response(404, json={}))
    assert await _client().inspect("gone") is None


@respx.mock
async def test_inspect_many_bounds_concurrency():
    import asyncio
    from oraclarr_mcp.clients import docker as mod
    active = peak = 0

    async def slow(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json=_fx("inspect_sonarr"))

    respx.get(url__regex=rf"{B}/containers/c\d+/json").mock(side_effect=slow)
    out = await _client().inspect_many([f"c{i}" for i in range(20)])
    assert len(out) == 20 and peak <= mod.INSPECT_CONCURRENCY


@respx.mock
async def test_logs_sends_tail_since_and_timestamps():
    route = respx.get(f"{B}/containers/abc/logs").mock(
        return_value=httpx.Response(200, content=_frame(1, b"T x\n")))
    raw = await _client().logs("abc", tail=50, since=1700000000)
    p = route.calls.last.request.url.params
    assert p["stdout"] == "1" and p["stderr"] == "1" and p["timestamps"] == "1"
    assert p["tail"] == "50" and p["since"] == "1700000000"
    assert raw == _frame(1, b"T x\n")


@respx.mock
async def test_403_raises_proxy_refused_without_query_string():
    respx.get(f"{B}/containers/abc/logs").mock(return_value=httpx.Response(403, text="no"))
    with pytest.raises(DockerProxyRefused) as e:
        await _client().logs("abc", tail=5, since=123)
    msg = str(e.value)
    assert "/containers/<id>/logs" in msg and "-allowGET" in msg and "tail" not in msg


@respx.mock
async def test_client_only_sends_get():
    respx.get(f"{B}/version").mock(return_value=httpx.Response(200, json=_fx("version")))
    respx.get(f"{B}/containers/json").mock(
        return_value=httpx.Response(200, json=_fx("containers")))
    respx.get(url__regex=rf"{B}/containers/[0-9a-f]+/json").mock(
        return_value=httpx.Response(200, json=_fx("inspect_sonarr")))
    respx.get(url__regex=rf"{B}/containers/[0-9a-f]+/logs").mock(
        return_value=httpx.Response(200, content=b""))
    c = _client()
    ids = [x["Id"] for x in await c.containers()]
    await c.version()
    await c.inspect_many(ids[:3])
    await c.logs(ids[0], tail=1)
    assert {call.request.method for call in respx.calls} == {"GET"}


HEX64 = re.compile(r"[0-9a-f]{64}")
CID = "ab" * 32


@respx.mock
async def test_403_message_hides_container_id():
    respx.get(f"{B}/containers/{CID}/json").mock(return_value=httpx.Response(403))
    with pytest.raises(DockerProxyRefused) as e:
        await _client().inspect(CID)
    assert not HEX64.search(str(e.value)) and "/containers/<id>/json" in str(e.value)


@respx.mock
async def test_logs_error_hides_id_and_query():
    respx.get(f"{B}/containers/{CID}/logs").mock(return_value=httpx.Response(501))
    with pytest.raises(DockerRequestFailed) as e:
        await _client().logs(CID, tail=50)
    msg = str(e.value)
    assert "501" in msg and "/containers/<id>/logs" in msg
    assert not HEX64.search(msg) and "tail" not in msg


@respx.mock
async def test_inspect_many_survives_one_failing_and_one_hung_inspect():
    respx.get(f"{B}/containers/c1/json").mock(return_value=httpx.Response(500))
    respx.get(f"{B}/containers/c2/json").mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get(f"{B}/containers/c3/json").mock(
        return_value=httpx.Response(200, json=_fx("inspect_sonarr")))
    out = await _client().inspect_many(["c1", "c2", "c3"])
    assert out[0] is None and out[1] is None and out[2]["Name"] == "/sonarr"


@respx.mock
async def test_inspect_error_is_not_cached():
    route = respx.get(f"{B}/containers/c1/json").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=_fx("inspect_sonarr"))])
    c = _client()
    assert (await c.inspect_many(["c1"]))[0] is None
    assert (await c.inspect_many(["c1"]))[0]["Name"] == "/sonarr"
    assert route.call_count == 2
