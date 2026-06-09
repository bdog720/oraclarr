from oraclarr_mcp.tools.quality_config import get_quality_config

class FakeArr:
    name="sonarr"; type="sonarr"
    async def quality_profiles(self): return [{"id": 1, "name": "HD"}]
    async def custom_formats(self): return [{"id": 5, "name": "English Dub"}]
    async def release_profiles(self): return [{"id": 2, "required": ["english"]}]

class FakeProfilarr:
    name="profilarr"; type="profilarr"
    async def status(self):
        return {
            "version": "2.0.8",
            "databases": [
                {"name": "Dictionarry", "lastSyncedAt": "2026-06-09T02:14:28Z",
                 "syncStrategy": "auto",
                 "counts": {"customFormats": 254, "qualityProfiles": 11}},
            ],
            "arrs": [
                {"name": "Sonarr", "type": "sonarr",
                 "sync": {"qualityProfiles": {"count": 5, "status": "idle"}},
                 "drift": None},
            ],
        }

async def test_quality_config_includes_arr_and_profilarr():
    res = await get_quality_config({"sonarr": FakeArr(), "profilarr": FakeProfilarr()})
    arr = [r for r in res if r["instance"] == "sonarr"][0]
    assert arr["data"]["profiles"][0]["name"] == "HD"
    assert arr["data"]["release_profiles"][0]["required"] == ["english"]
    prof = [r for r in res if r["instance"] == "profilarr"][0]
    assert prof["data"]["version"] == "2.0.8"
    assert prof["data"]["databases"][0]["counts"]["qualityProfiles"] == 11
    assert prof["data"]["arrs"][0]["name"] == "Sonarr"
