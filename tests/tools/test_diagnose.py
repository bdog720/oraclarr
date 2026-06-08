from oraclarr_mcp.tools.diagnose import diagnose

class FakeArr:
    name="sonarr"; type="sonarr"
    async def lookup_library(self, term, media):
        return [{"title": "Show", "id": 7, "tvdbId": 111}] if term.lower() in "show" else []
    async def queue(self):
        return [{"title": "Show.S03E04", "seriesId": 7, "downloadId": "H1",
                 "trackedDownloadState": "downloading", "size": 100, "sizeleft": 50}]
    async def wanted_missing(self):
        return [{"title": "Show", "seriesId": 7}]

async def test_diagnose_reports_found_and_in_queue():
    res = await diagnose({"sonarr": FakeArr()}, title="Show")
    assert res["matches"][0]["instance"] == "sonarr"
    assert res["matches"][0]["in_library"] is True
    assert res["matches"][0]["in_queue"] is True
    assert res["matches"][0]["wanted"] is True

async def test_diagnose_no_match():
    res = await diagnose({"sonarr": FakeArr()}, title="Nonexistent")
    assert res["matches"] == []
