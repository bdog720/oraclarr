from oraclarr_mcp.tools.explain_decision import explain_decision

class FakeArr:
    name="sonarr"; type="sonarr"
    async def lookup_library(self, term, media):
        return [{"title": "Anime", "id": 9, "qualityProfileId": 3}]
    async def quality_profiles(self):
        return [{"id": 3, "name": "HD-Anime", "cutoff": 1080,
                 "minFormatScore": 0, "cutoffFormatScore": 100,
                 "formatItems": [{"name": "English Dub", "score": 50},
                                 {"name": "Subbed Only", "score": -100}]}]
    async def history(self, limit=30):
        return [{"sourceTitle": "Anime.S01E01.Subbed", "eventType": "grabbed",
                 "seriesId": 9, "customFormatScore": -100,
                 "customFormats": [{"name": "Subbed Only"}]}]

async def test_explain_surfaces_profile_and_grab():
    res = await explain_decision({"sonarr": FakeArr()}, title="Anime")
    m = res["matches"][0]
    assert m["profile"]["name"] == "HD-Anime"
    assert m["profile"]["cutoff_format_score"] == 100
    assert m["recent_grabs"][0]["score"] == -100
    assert any(f["name"] == "Subbed Only" for f in m["profile"]["format_scores"])

async def test_explain_no_match_returns_empty():
    res = await explain_decision({"sonarr": FakeArr()}, title="Nope")
    assert isinstance(res["matches"], list)
