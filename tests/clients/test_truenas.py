import json
import ssl
from pathlib import Path

import pytest

from oraclarr_mcp.clients.truenas import (
    CACHE_TTL_S, TruenasAuthError, TruenasCallError, TruenasClient, ws_url,
)

FX = Path(__file__).parent.parent / "fixtures"
KEY = "TNKEY-SECRET-1"


def _fx(name):
    return json.loads((FX / f"truenas_{name}.json").read_text(encoding="utf-8"))


class FakeWS:
    """Answers each request from a method -> result table; can inject a notification."""

    def __init__(self, replies, notify_first=False):
        self.sent = []
        self.replies = replies
        self.notify_first = notify_first

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        if self.notify_first:
            self.notify_first = False
            return json.dumps({"jsonrpc": "2.0", "method": "collection_update", "params": {}})
        req = self.sent[-1]
        rep = self.replies[req["method"]]
        if isinstance(rep, dict) and "__error__" in rep:
            return json.dumps({"jsonrpc": "2.0", "id": req["id"], "error": rep["__error__"]})
        return json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": rep})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Clock:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


def _client(ws, seen=None, verify_tls=True, clock=None):
    def connect(uri, ssl_ctx, timeout):
        if seen is not None:
            seen.append((uri, ssl_ctx))
        return ws
    return TruenasClient("truenas", "truenas", "https://nas", KEY, 5, verify_tls=verify_tls,
                         connect=connect, clock=clock or Clock())


BASE = {"auth.login_with_api_key": True}


def test_ws_url_requires_https():
    assert ws_url("https://nas/") == "wss://nas/api/current"
    with pytest.raises(ValueError):
        ws_url("http://nas")


async def test_login_first_and_key_never_in_url():
    seen = []
    ws = FakeWS({**BASE, "system.info": _fx("system_info")})
    c = _client(ws, seen)
    info = await c.system_info()
    assert ws.sent[0] == {"jsonrpc": "2.0", "id": 1, "method": "auth.login_with_api_key",
                          "params": [KEY]}
    assert ws.sent[1]["method"] == "system.info"
    assert KEY not in seen[0][0]
    assert info["version"]  # live system.info reports "25.10.7" (no "TrueNAS-" prefix)


async def test_notifications_are_skipped():
    ws = FakeWS({**BASE, "system.info": _fx("system_info")}, notify_first=True)
    assert (await _client(ws).system_info())["version"]


async def test_failed_login_raises_auth_error():
    ws = FakeWS({"auth.login_with_api_key": False})
    with pytest.raises(TruenasAuthError):
        await _client(ws).system_info()


async def test_error_reply_drops_trace():
    err = {"code": -32001, "message": "Method call error",
           "data": {"error": 22, "errname": "EINVAL", "reason": "bad graph",
                    "trace": {"class": "KeyError",
                              "frames": [{"locals": {"secret": "LOCAL-SECRET-9"}}]}}}
    ws = FakeWS({**BASE, "pool.query": {"__error__": err}})
    with pytest.raises(TruenasCallError) as e:
        await _client(ws).pools()
    msg = str(e.value)
    assert "Method call error" in msg and "bad graph" in msg
    assert "LOCAL-SECRET-9" not in msg and "frames" not in msg


async def test_methods_send_expected_params():
    ws = FakeWS({**BASE, "pool.query": _fx("pools"), "pool.dataset.query": _fx("datasets"),
                 "alert.list": _fx("alerts")})
    c = _client(ws)
    await c.pools()
    await c.datasets()
    await c.alerts()
    sent = {m["method"]: m["params"] for m in ws.sent}
    assert sent["pool.query"][1]["select"] == ["name", "status", "healthy", "size", "allocated",
                                               "free", "fragmentation", "scan"]
    assert sent["pool.dataset.query"][0] == [["type", "=", "FILESYSTEM"]]
    assert sent["pool.dataset.query"][1]["extra"] == {"flat": True, "retrieve_children": True}
    assert sent["alert.list"] == []


async def test_disk_temps_query_each_identifier():
    graphs = _fx("graphs")
    ws = FakeWS({**BASE, "reporting.netdata_graphs": graphs,
                 "reporting.netdata_get_data": _fx("disktemp_data")})
    temps = await _client(ws).disk_temps()
    req = next(m for m in ws.sent if m["method"] == "reporting.netdata_get_data")
    ids = next(g["identifiers"] for g in graphs if g["name"] == "disktemp")
    assert [g["identifier"] for g in req["params"][0]] == ids
    assert all(g["name"] == "disktemp" for g in req["params"][0])
    assert req["params"][1]["aggregate"] is True
    assert {"identifier", "temp_c"} <= set(temps[0])


async def test_verify_tls_false_disables_certificate_checks():
    seen = []
    ws = FakeWS({**BASE, "system.info": _fx("system_info")})
    await _client(ws, seen, verify_tls=False).system_info()
    ctx = seen[0][1]
    assert ctx.verify_mode == ssl.CERT_NONE and ctx.check_hostname is False


async def test_verify_tls_default_checks_certificates():
    seen = []
    ws = FakeWS({**BASE, "system.info": _fx("system_info")})
    await _client(ws, seen).system_info()
    assert seen[0][1].verify_mode == ssl.CERT_REQUIRED


async def test_truenas_cache_ttl():
    seen = []
    clock = Clock()
    ws = FakeWS({**BASE, "system.info": _fx("system_info")})
    c = _client(ws, seen, clock=clock)
    await c.system_info()
    await c.system_info()
    assert len(seen) == 1
    clock.t += CACHE_TTL_S + 1
    await c.system_info()
    assert len(seen) == 2
