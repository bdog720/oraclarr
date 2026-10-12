import json

from oraclarr_mcp.tools.cleanup import get_cleanup, strike_row

QB_PASS = "QBPASS-SECRET-1"
AUTH_KEY = "CLKEY-SECRET-2"

GENERAL = {"dryRun": True, "strikeInactivityWindowHours": 24, "historyRetentionDays": 365,
           "ignoredDownloads": ["a", "b"], "httpTimeout": 100,
           "auth": {"apiKey": AUTH_KEY, "password": "x"}}
CLIENTS = [{"id": "c1", "enabled": True, "name": "qBittorrent", "typeName": "qBittorrent",
            "type": "Torrent", "host": "http://10.9.9.9:8080", "username": "admin",
            "password": QB_PASS}]
SEEDING = [{"id": "r1", "name": "Private", "categories": ["tv"], "trackerPatterns": [],
            "tagsAny": [], "tagsAll": [], "priority": 1, "privacyType": "Private",
            "maxRatio": 2, "minSeedTime": 72, "maxSeedTime": 168, "minSeeders": 0,
            "maxInactiveDays": -1, "deleteSourceFiles": True, "action": "Remove"}]
UNLINKED = {"enabled": False, "targetCategory": "cleanuparr-unlinked", "useTag": False,
            "ignoredRootDirs": ["/data/x"], "categories": ["tv"]}
STALL = [{"id": "s1", "name": "Stalled (public)", "enabled": True, "maxStrikes": 10,
          "privacyType": "Public", "minCompletionPercentage": 0,
          "maxCompletionPercentage": 95, "resetStrikesOnProgress": True,
          "deletePrivateTorrentsFromClient": False, "changeCategory": False}]
SLOW = [{**STALL[0], "id": "s2", "name": "Slow", "minSpeed": "100KB", "maxTimeHours": 24,
         "ignoreAboveSize": "50GB", "ignoreWhileAltSpeedActive": True}]
QUEUE_CLEANER = {"enabled": True, "cronExpression": "0 */5 * * * ?",
                 "failedImport": {"maxStrikes": 5, "ignorePrivate": True,
                                  "deletePrivate": False, "patterns": ["x"],
                                  "patternMode": "Exclude", "forceImport": False}}
CLEANERS = {"queue_cleaner": QUEUE_CLEANER,
            "download_cleaner": {"enabled": True, "cronExpression": "0 0 * * * ?"},
            "malware_blocker": {"enabled": False, "cronExpression": "0 */5 * * *"},
            "blacklist_sync": {"enabled": False, "cronExpression": "0 0 * * *"},
            "seeker": {"searchEnabled": True, "searchInterval": 10, "instances": [{"x": 1}]}}
JOBS = [{"name": "QueueCleaner", "status": "Scheduled", "schedule": "0 */5 * * * ?",
         "previousRunTime": "2026-10-12T10:00:00Z", "nextRunTime": "2026-10-12T10:05:00Z",
         "jobType": "QueueCleaner"},
        {"name": "MalwareBlocker", "status": "Not Scheduled", "schedule": "",
         "previousRunTime": None, "nextRunTime": None, "jobType": "MalwareBlocker"}]
STRIKES = [{"downloadItemId": f"i{i}", "downloadId": f"{i:040x}", "title": f"Show {i}",
            "totalStrikes": 3, "strikesByType": {"Stalled": 3},
            "latestStrikeAt": "2026-10-12T10:00:00Z", "firstStrikeAt": "2026-10-11T10:00:00Z",
            "isMarkedForRemoval": i == 0, "isRemoved": False, "isReturning": False,
            "hasDryRunStrikes": False, "strikes": [{"id": "x"}]} for i in range(30)]
RECENT = [{"id": f"e{i}", "type": "Stalled", "createdAt": f"2026-10-12T0{i}:00:00Z",
           "downloadId": f"{i:040x}", "title": f"Show {i}", "isDryRun": False}
          for i in range(8)]


class FakeCl:
    name = "cleanuparr"; type = "cleanuparr"

    def __init__(self, clients=None):
        self.calls = []
        self._clients = CLIENTS if clients is None else clients

    async def general(self):
        self.calls.append("general")
        return GENERAL

    async def cleaner_config(self, name):
        self.calls.append(("cleaner", name))
        return CLEANERS[name]

    async def download_clients(self):
        return self._clients

    async def seeding_rules(self, cid):
        assert cid == "c1"
        return SEEDING

    async def unlinked_config(self, cid):
        return UNLINKED

    async def stall_rules(self):
        return STALL

    async def slow_rules(self):
        return SLOW

    async def jobs(self):
        self.calls.append("jobs")
        return JOBS

    async def strikes(self, page_size):
        self.calls.append(("strikes", page_size))
        return STRIKES[:page_size], len(STRIKES)

    async def recent_strikes(self):
        return list(reversed(RECENT))


async def test_summary_shape():
    row = (await get_cleanup({"cleanuparr": FakeCl()}))[0]
    assert row["status"] == "ok"
    d = row["data"]
    assert d["dry_run"] is True
    assert [j["name"] for j in d["jobs"]] == ["QueueCleaner", "MalwareBlocker"]
    assert d["jobs"][0] == {"name": "QueueCleaner", "status": "Scheduled",
                            "schedule": "0 */5 * * * ?", "last_run": "2026-10-12T10:00:00Z",
                            "next_run": "2026-10-12T10:05:00Z"}
    assert d["strikes"]["downloads"] == 30
    assert d["strikes"]["marked_for_removal"] == 1
    assert [r["at"] for r in d["strikes"]["recent"]] == [
        "2026-10-12T07:00:00Z", "2026-10-12T06:00:00Z", "2026-10-12T05:00:00Z",
        "2026-10-12T04:00:00Z", "2026-10-12T03:00:00Z"]
    assert d["strikes"]["recent"][0] == {"type": "Stalled", "title": "Show 7",
                                         "at": "2026-10-12T07:00:00Z", "dry_run": False}


async def test_rules_section():
    d = (await get_cleanup({"cleanuparr": FakeCl()}, section="rules"))[0]["data"]
    assert d["clients"][0]["client"] == {"name": "qBittorrent", "type": "qBittorrent",
                                         "enabled": True}
    assert d["clients"][0]["seeding_rules"][0] == {
        "name": "Private", "privacy": "Private", "categories": ["tv"], "tracker_patterns": [],
        "max_ratio": 2, "min_seed_hours": 72, "max_seed_hours": 168, "min_seeders": 0,
        "max_inactive_days": -1, "action": "Remove", "delete_source_files": True}
    assert d["clients"][0]["unlinked"] == {"enabled": False,
                                           "target_category": "cleanuparr-unlinked",
                                           "use_tag": False, "categories": ["tv"],
                                           "ignored_root_dirs": ["/data/x"]}
    assert d["stall_rules"][0] == {"name": "Stalled (public)", "enabled": True,
                                   "max_strikes": 10, "privacy": "Public",
                                   "min_completion": 0, "max_completion": 95,
                                   "reset_on_progress": True}
    assert d["slow_rules"][0]["min_speed"] == "100KB"
    assert d["slow_rules"][0]["max_time_hours"] == 24
    assert d["slow_rules"][0]["ignore_above_size"] == "50GB"
    assert d["failed_import"] == {"max_strikes": 5, "ignore_private": True,
                                  "delete_private": False, "patterns": ["x"],
                                  "pattern_mode": "Exclude"}


async def test_config_section():
    d = (await get_cleanup({"cleanuparr": FakeCl()}, section="config"))[0]["data"]
    assert d["dry_run"] is True and d["ignored_downloads"] == 2
    assert d["strike_inactivity_hours"] == 24 and d["history_retention_days"] == 365
    assert d["cleaners"]["queue_cleaner"] == {"enabled": True, "schedule": "0 */5 * * * ?"}
    assert d["cleaners"]["seeker"] == {"enabled": True, "interval_minutes": 10}
    assert set(d["cleaners"]) == {"queue_cleaner", "download_cleaner", "malware_blocker",
                                  "blacklist_sync", "seeker"}


async def test_rules_and_config_never_emit_secrets():
    out = [await get_cleanup({"cleanuparr": FakeCl()}, section=s)
           for s in ("rules", "config", None)]
    text = json.dumps(out)
    for secret in (QB_PASS, AUTH_KEY, "admin", "10.9.9.9", "auth"):
        assert secret not in text


async def test_rules_with_no_download_clients():
    d = (await get_cleanup({"cleanuparr": FakeCl(clients=[])}, section="rules"))[0]["data"]
    assert d["clients"] == []


async def test_strikes_section_bounds():
    fake = FakeCl()
    row = (await get_cleanup({"cleanuparr": fake}, section="strikes", limit=5))[0]
    assert len(row["data"]) == 5 and row["total"] == 30 and row["truncated"] is True
    assert ("strikes", 5) in fake.calls
    assert row["data"][0] == strike_row(STRIKES[0])
    assert row["data"][0] == {"download_id": f"{0:040x}", "title": "Show 0",
                              "total_strikes": 3, "by_type": {"Stalled": 3},
                              "first_at": "2026-10-11T10:00:00Z",
                              "latest_at": "2026-10-12T10:00:00Z",
                              "marked_for_removal": True, "removed": False, "dry_run": False}


async def test_jobs_section():
    d = (await get_cleanup({"cleanuparr": FakeCl()}, section="jobs"))[0]["data"]
    assert [j["status"] for j in d] == ["Scheduled", "Not Scheduled"]


async def test_invalid_section_without_upstream_calls():
    fake = FakeCl()
    out = await get_cleanup({"cleanuparr": fake}, section="secrets")
    assert out == {"error": "invalid_section", "valid": ["config", "jobs", "rules", "strikes"]}
    assert fake.calls == []


async def test_limit_is_clamped():
    fake = FakeCl()
    await get_cleanup({"cleanuparr": fake}, section="strikes", limit=0)
    await get_cleanup({"cleanuparr": fake}, section="strikes", limit=10_000)
    assert ("strikes", 1) in fake.calls and ("strikes", 100) in fake.calls


async def test_only_cleanuparr_instances_are_queried():
    class Arr:
        name = "sonarr"; type = "sonarr"
    out = await get_cleanup({"sonarr": Arr(), "cleanuparr": FakeCl()}, section="jobs")
    assert [r["instance"] for r in out] == ["cleanuparr"]


async def test_summary_qualifies_strike_counts():
    class Partial(FakeCl):
        async def strikes(self, page_size):
            rows = [{**STRIKES[0], "isRemoved": True}, STRIKES[1], STRIKES[2]]
            return rows, 340

    s = (await get_cleanup({"cleanuparr": Partial()}))[0]["data"]["strikes"]
    assert s["downloads"] == 340
    assert s["scanned"] == 3 and s["complete"] is False
    assert s["active"] == 2
    assert s["marked_for_removal"] == 1


async def test_summary_complete_when_all_rows_scanned():
    s = (await get_cleanup({"cleanuparr": FakeCl()}))[0]["data"]["strikes"]
    assert s["scanned"] == 30 and s["complete"] is True and s["active"] == 30
