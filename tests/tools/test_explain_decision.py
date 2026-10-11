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
    async def item_history(self, item_id, media):
        assert media == "series"
        if item_id != 9:
            return []
        return [{"sourceTitle": "Anime.S01E01.Subbed", "eventType": "grabbed",
                 "seriesId": 9, "customFormatScore": -100,
                 "customFormats": [{"name": "Subbed Only"}]},
                {"sourceTitle": "Anime.S01E01.Subbed", "eventType": "downloadFolderImported",
                 "seriesId": 9, "customFormatScore": -100, "customFormats": []}]

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


class ManyArr(FakeArr):
    def __init__(self):
        self.history_calls = 0
    async def lookup_library(self, term, media):
        return [{"title": f"The Thing {i}", "id": 100 + i, "qualityProfileId": 3}
                for i in range(25)]
    async def item_history(self, item_id, media):
        self.history_calls += 1
        return []


async def test_explain_examines_at_most_ten_items():
    fake = ManyArr()
    res = await explain_decision({"sonarr": fake}, title="the")
    assert len(res["matches"]) == 10
    assert res["truncated"] is True
    assert fake.history_calls == 10


class BrokenProfiles(FakeArr):
    name = "broken"
    async def quality_profiles(self):
        raise RuntimeError("profiles down")


async def test_explain_reports_failing_instance_and_keeps_peers():
    res = await explain_decision({"sonarr": FakeArr(), "broken": BrokenProfiles()},
                                 title="Anime")
    assert [m["instance"] for m in res["matches"]] == ["sonarr"]
    assert res["errors"][0]["instance"] == "broken"
