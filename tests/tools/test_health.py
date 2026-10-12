from oraclarr_mcp.tools.health import stack_health
from oraclarr_mcp.clients.arr import ArrClient

class FakeArr(ArrClient):
    def __init__(self, ok=True): self._ok = ok; self.name="sonarr"; self.type="sonarr"
    async def system_status(self): return {"version": "4.0"}
    async def health(self): return [{"message": "warn"}] if not self._ok else []
    async def diskspace(self): return [{"path": "/tv", "freeSpace": 5, "totalSpace": 100}]
    async def aclose(self): pass

async def test_stack_health_reports_ok_instance():
    clients = {"sonarr": FakeArr(ok=True)}
    res = await stack_health(clients)
    row = [r for r in res if r["instance"] == "sonarr"][0]
    assert row["status"] == "ok"
    assert row["data"]["version"] == "4.0"

async def test_stack_health_surfaces_unreachable():
    class Dead(FakeArr):
        async def system_status(self): raise __import__("httpx").ConnectError("down")
    res = await stack_health({"sonarr": Dead()})
    assert res[0]["status"] == "unreachable"


async def test_stack_health_projects_disks():
    res = await stack_health({"sonarr": FakeArr(ok=True)})
    assert res[0]["data"]["disks"] == [{"path": "/tv", "free_space": 5, "total_space": 100}]


class FakeJf:
    name = "jellyfin"; type = "jellyfin"
    async def system_info(self):
        return {"Version": "12.2.0", "HasPendingRestart": True, "HasUpdateAvailable": False,
                "LocalAddress": "http://x", "ProgramDataPath": "/config"}
    async def scheduled_tasks(self):
        return [{"Name": "Scan Media Library", "LastExecutionResult": {"Status": "Completed"}},
                {"Name": "Extract Chapter Images", "LastExecutionResult": {"Status": "Failed"}},
                {"Name": "Never Ran"}]


async def test_stack_health_reports_jellyfin():
    row = (await stack_health({"jellyfin": FakeJf()}))[0]
    assert row["status"] == "ok"
    assert row["data"] == {"version": "12.2.0", "pending_restart": True,
                           "update_available": False,
                           "failed_tasks": ["Extract Chapter Images"]}


class FakeCl:
    name = "cleanuparr"; type = "cleanuparr"
    async def general(self):
        return {"dryRun": False, "auth": {"apiKey": "SECRET-AUTH-9"}}
    async def jobs(self):
        return [{"name": "QueueCleaner", "status": "Scheduled"},
                {"name": "MalwareBlocker", "status": "Not Scheduled"},
                {"name": "Seeker", "status": "Scheduled"}]


async def test_stack_health_reports_cleanuparr():
    row = (await stack_health({"cleanuparr": FakeCl()}))[0]
    assert row["status"] == "ok"
    assert row["data"] == {"dry_run": False, "scheduled_jobs": ["QueueCleaner", "Seeker"],
                           "unscheduled_jobs": ["MalwareBlocker"]}


async def test_stack_health_cleanuparr_running_job_counts_as_scheduled():
    import json
    from pathlib import Path
    live = json.loads((Path(__file__).parent.parent / "fixtures" / "cleanuparr_jobs.json")
                      .read_text(encoding="utf-8"))
    assert any(j["status"] == "Running" for j in live)  # the live state the spec missed

    class LiveCl(FakeCl):
        async def jobs(self):
            return live

    d = (await stack_health({"cleanuparr": LiveCl()}))[0]["data"]
    assert d["unscheduled_jobs"] == [j["name"] for j in live if j["status"] == "Not Scheduled"]
    assert d["scheduled_jobs"] == [j["name"] for j in live if j["status"] != "Not Scheduled"]
