import json
from pathlib import Path

import httpx
import respx

from oraclarr_mcp.clients.base import MediaBrowserTokenAuth
from oraclarr_mcp.clients.jellyfin import JellyfinClient

FX = Path(__file__).parent.parent / "fixtures"


def _fx(name):
    return json.loads((FX / f"jellyfin_{name}.json").read_text(encoding="utf-8"))


def _client():
    return JellyfinClient("jellyfin", "jellyfin", "http://h", MediaBrowserTokenAuth("K"), timeout=5)


@respx.mock
async def test_auth_header_is_mediabrowser_token():
    route = respx.get("http://h/System/Info").mock(
        return_value=httpx.Response(200, json=_fx("system_info")))
    c = _client()
    info = await c.system_info()
    assert route.calls.last.request.headers["Authorization"] == 'MediaBrowser Token="K"'
    assert "api_key" not in str(route.calls.last.request.url)
    assert info["Version"]
    await c.aclose()


@respx.mock
async def test_virtual_folders_returns_list_with_refresh_state():
    respx.get("http://h/Library/VirtualFolders").mock(
        return_value=httpx.Response(200, json=_fx("virtual_folders")))
    c = _client()
    folders = await c.virtual_folders()
    assert isinstance(folders, list) and folders
    assert {"Name", "ItemId", "RefreshStatus"} <= set(folders[0])
    await c.aclose()


@respx.mock
async def test_library_count_reads_total_record_count():
    route = respx.get("http://h/Items").mock(
        return_value=httpx.Response(200, json={"Items": [], "TotalRecordCount": 42}))
    c = _client()
    assert await c.library_count("lib1") == 42
    p = route.calls.last.request.url.params
    assert p["parentId"] == "lib1" and p["recursive"] == "true"
    assert p["enableTotalRecordCount"] == "true"
    await c.aclose()


@respx.mock
async def test_search_items_params_and_result():
    route = respx.get("http://h/Items").mock(
        return_value=httpx.Response(200, json=_fx("items_search")))
    c = _client()
    items, total = await c.search_items("Procedural", 5)
    p = route.calls.last.request.url.params
    assert p["searchTerm"] == "Procedural"
    assert p["includeItemTypes"] == "Series,Movie"
    assert p["fields"] == "ProviderIds,Path,DateCreated"
    assert p["limit"] == "5"
    assert items and "ProviderIds" in items[0]
    assert total >= len(items)
    await c.aclose()


@respx.mock
async def test_recent_items_sorted_newest_first():
    route = respx.get("http://h/Items").mock(
        return_value=httpx.Response(200, json=_fx("items_recent")))
    c = _client()
    items, total = await c.recent_items(5)
    p = route.calls.last.request.url.params
    assert p["sortBy"] == "DateCreated" and p["sortOrder"] == "Descending"
    assert p["includeItemTypes"] == "Episode,Movie"
    assert total >= len(items)
    await c.aclose()


@respx.mock
async def test_sessions_and_tasks_paths():
    s = respx.get("http://h/Sessions").mock(
        return_value=httpx.Response(200, json=_fx("sessions")))
    t = respx.get("http://h/ScheduledTasks").mock(
        return_value=httpx.Response(200, json=_fx("scheduled_tasks")))
    c = _client()
    assert isinstance(await c.sessions(), list)
    tasks = await c.scheduled_tasks()
    assert s.calls.last.request.url.params["activeWithinSeconds"] == "960"
    assert t.calls.last.request.url.params["isHidden"] == "false"
    assert {"Name", "State"} <= set(tasks[0])
    await c.aclose()
