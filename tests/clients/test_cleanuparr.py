import json
from pathlib import Path

import httpx
import pytest
import respx

from oraclarr_mcp.clients.base import ApiKeyHeaderAuth
from oraclarr_mcp.clients.cleanuparr import CLEANER_NAMES, CleanuparrClient

FX = Path(__file__).parent.parent / "fixtures"
B = "http://h"


def _fx(name):
    return json.loads((FX / f"cleanuparr_{name}.json").read_text(encoding="utf-8"))


def _client():
    return CleanuparrClient("cleanuparr", "cleanuparr", B, ApiKeyHeaderAuth("K"), timeout=5)


@respx.mock
async def test_general_sends_x_api_key_header():
    route = respx.get(f"{B}/api/configuration/general").mock(
        return_value=httpx.Response(200, json=_fx("general")))
    c = _client()
    g = await c.general()
    req = route.calls.last.request
    assert req.headers["X-Api-Key"] == "K"
    assert "apikey" not in str(req.url).lower()
    assert "dryRun" in g
    await c.aclose()


@respx.mock
async def test_download_clients_unwraps_clients():
    respx.get(f"{B}/api/configuration/download_client").mock(
        return_value=httpx.Response(200, json=_fx("download_client")))
    c = _client()
    clients = await c.download_clients()
    assert isinstance(clients, list) and {"id", "name", "typeName"} <= set(clients[0])
    await c.aclose()


@respx.mock
async def test_cleaner_config_paths():
    for name in CLEANER_NAMES:
        respx.get(f"{B}/api/configuration/{name}").mock(
            return_value=httpx.Response(200, json={"enabled": True}))
    c = _client()
    for name in CLEANER_NAMES:
        assert (await c.cleaner_config(name)) == {"enabled": True}
    await c.aclose()


async def test_cleaner_config_rejects_unknown_names():
    c = _client()
    with pytest.raises(ValueError):
        await c.cleaner_config("notification_providers")
    await c.aclose()


@respx.mock
async def test_per_client_rule_paths():
    s = respx.get(f"{B}/api/seeding-rules/c1").mock(
        return_value=httpx.Response(200, json=_fx("seeding_rules")))
    u = respx.get(f"{B}/api/unlinked-config/c1").mock(
        return_value=httpx.Response(200, json=_fx("unlinked")))
    c = _client()
    assert isinstance(await c.seeding_rules("c1"), list)
    assert "targetCategory" in await c.unlinked_config("c1")
    assert s.called and u.called
    await c.aclose()


@respx.mock
async def test_queue_rules_and_jobs():
    respx.get(f"{B}/api/queue-rules/stall").mock(
        return_value=httpx.Response(200, json=_fx("stall_rules")))
    respx.get(f"{B}/api/queue-rules/slow").mock(
        return_value=httpx.Response(200, json=_fx("slow_rules")))
    respx.get(f"{B}/api/jobs").mock(return_value=httpx.Response(200, json=_fx("jobs")))
    c = _client()
    assert "maxStrikes" in (await c.stall_rules())[0]
    assert "minSpeed" in (await c.slow_rules())[0]
    assert {"name", "status"} <= set((await c.jobs())[0])
    await c.aclose()


@respx.mock
async def test_strikes_pages_and_returns_total():
    route = respx.get(f"{B}/api/strikes").mock(
        return_value=httpx.Response(200, json=_fx("strikes")))
    c = _client()
    items, total = await c.strikes(7)
    p = route.calls.last.request.url.params
    assert p["page"] == "1" and p["pageSize"] == "7"
    assert total >= len(items) and "downloadId" in items[0]
    await c.aclose()


@respx.mock
async def test_strikes_treats_null_items_as_empty():
    respx.get(f"{B}/api/strikes").mock(
        return_value=httpx.Response(200, json={"items": None, "totalCount": 0}))
    c = _client()
    assert await c.strikes(5) == ([], 0)
    await c.aclose()


@respx.mock
async def test_recent_strikes():
    respx.get(f"{B}/api/strikes/recent").mock(
        return_value=httpx.Response(200, json=_fx("strikes_recent")))
    c = _client()
    assert {"type", "downloadId", "createdAt"} <= set((await c.recent_strikes())[0])
    await c.aclose()
