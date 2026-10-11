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


class RichArr(FakeArr):
    async def quality_profiles(self):
        return [{"id": 1, "name": "HD", "cutoff": 7, "upgradeAllowed": True,
                 "minFormatScore": 0, "cutoffFormatScore": 100,
                 "items": [{"quality": {"name": "HDTV-720p"}}],
                 "formatItems": [{"format": 5, "name": "English Dub", "score": 50},
                                 {"format": 6, "name": "Noise", "score": 0}]}]
    async def custom_formats(self):
        return [{"id": 5, "name": "English Dub",
                 "specifications": [{"name": "regex", "fields": [{"value": "dub"}]}]}]
    async def release_profiles(self):
        return [{"id": 2, "name": "Eng", "enabled": True,
                 "required": ["english"], "ignored": ["fr"], "indexerId": 0}]


async def test_quality_config_projects_profiles_and_formats():
    res = await get_quality_config({"sonarr": RichArr()})
    d = res[0]["data"]
    assert d["profiles"] == [{
        "id": 1, "name": "HD", "cutoff": 7, "upgrade_allowed": True,
        "min_format_score": 0, "cutoff_format_score": 100,
        "format_scores": [{"name": "English Dub", "score": 50}],
    }]
    assert d["custom_formats"] == [{"id": 5, "name": "English Dub"}]
    assert d["release_profiles"] == [{"name": "Eng", "enabled": True,
                                      "required": ["english"], "ignored": ["fr"]}]
