from types import SimpleNamespace

import httpx

from oraclarr_mcp.tools.health import stack_health
from oraclarr_mcp.clients.arr import ArrClient

from .test_containers import FakeDocker, _default_inspects

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


class FakeNd:
    name = "netdata"; type = "netdata"
    async def info(self):
        return {"version": "v2.12.1", "machine_guid": "GUID-PRIVATE"}
    async def latest(self, ctx):
        return {"user": 1.0} if ctx == "system.cpu" else {}


class FakeTn:
    name = "truenas"; type = "truenas"
    async def system_info(self):
        return {"version": "25.10.7", "system_serial": "SERIAL-PRIVATE"}
    async def pools(self):
        return [{"healthy": True}, {"healthy": True}]
    async def alerts(self):
        return [{"level": "WARNING", "dismissed": False}, {"level": "INFO", "dismissed": True}]
    async def summary(self):
        return await self.system_info(), await self.pools(), await self.alerts()


async def test_stack_health_reports_netdata_and_truenas():
    rows = {r["instance"]: r for r in await stack_health({"netdata": FakeNd(),
                                                          "truenas": FakeTn()})}
    assert rows["netdata"]["data"] == {"version": "v2.12.1", "collecting": True}
    assert rows["truenas"]["data"] == {"version": "25.10.7", "pools_healthy": True,
                                       "alerts": {"WARNING": 1}}


class BatchTn:
    name = "truenas"; type = "truenas"
    async def summary(self):
        return ({"version": "25.10.7"}, [{"healthy": True}], [])


async def test_stack_health_truenas_uses_one_batch():
    row = (await stack_health({"truenas": BatchTn()}))[0]
    assert row["status"] == "ok"
    assert row["data"] == {"version": "25.10.7", "pools_healthy": True, "alerts": {}}


class FakeDockerHealth(FakeDocker):
    async def version(self):
        return {"Version": "28.3.1", "ApiVersion": "1.51"}


def _down(name, type, url):
    class Down:
        async def system_status(self):
            raise httpx.ConnectError("down")
        async def transfer_info(self):
            raise httpx.ConnectError("down")
    d = Down()
    d.name, d.type = name, type
    d.http = SimpleNamespace(base_url=httpx.URL(url))
    return d


async def test_stack_health_docker_row_counts_from_list():
    res = await stack_health({"docker": FakeDockerHealth()})
    data = res[0]["data"]
    assert data["version"] == "28.3.1"
    assert data["containers"]["running"] == 23 and "problems" not in data["containers"]


async def test_unreachable_instance_gets_port_owner_and_network_sharers():
    clients = {"qbit": _down("qbit", "qbittorrent", "http://192.0.2.10:8080"),
               "docker": FakeDockerHealth(None, _default_inspects())}
    res = await stack_health(clients)
    row = next(r for r in res if r["instance"] == "qbit")
    assert row["status"] == "unreachable"
    assert [c["name"] for c in row["container"]] == ["gluetun", "qbittorrent"]
    assert set(row["container"][0]) == {"name", "state", "health", "exit_code",
                                        "restart_count", "finished_at"}


async def test_unpublished_port_gives_null_container():
    clients = {"x": _down("x", "sonarr", "http://h:4444"), "docker": FakeDockerHealth()}
    res = await stack_health(clients)
    assert next(r for r in res if r["instance"] == "x")["container"] is None


async def test_instance_target_is_host_and_explicit_port():
    from oraclarr_mcp.tools.containers import instance_target
    assert instance_target(_down("a", "sonarr", "https://h")) == ("h", None)
    assert instance_target(_down("a", "sonarr", "http://Sonarr-Anime:8989")) == (
        "sonarr-anime", 8989)
    assert instance_target(SimpleNamespace()) is None


async def test_url_hostname_matches_container_before_port():
    # sonarr publishes 8989; sonarr-anime is reached by container name on its own 8989.
    clients = {"sonarr-anime": _down("sonarr-anime", "sonarr", "http://sonarr-anime:8989"),
               "docker": FakeDockerHealth(None, _default_inspects())}
    res = await stack_health(clients)
    row = next(r for r in res if r["instance"] == "sonarr-anime")
    assert [c["name"] for c in row["container"]] == ["sonarr-anime"]


async def test_no_explicit_port_and_unknown_host_skips_join():
    clients = {"sonarr": _down("sonarr", "sonarr", "https://sonarr.example.com"),
               "docker": FakeDockerHealth()}
    res = await stack_health(clients)
    assert "container" not in next(r for r in res if r["instance"] == "sonarr")


async def test_no_join_with_two_docker_instances():
    d2 = FakeDockerHealth()
    d2.name = "docker2"
    clients = {"qbit": _down("qbit", "qbittorrent", "http://h:8080"),
               "docker": FakeDockerHealth(), "docker2": d2}
    res = await stack_health(clients)
    assert "container" not in next(r for r in res if r["instance"] == "qbit")


async def test_docker_failure_leaves_rows_unchanged():
    class Broken(FakeDockerHealth):
        async def containers(self):
            raise httpx.ConnectError("proxy down")
    clients = {"qbit": _down("qbit", "qbittorrent", "http://h:8080"), "docker": Broken()}
    res = await stack_health(clients)
    assert "container" not in next(r for r in res if r["instance"] == "qbit")
    assert next(r for r in res if r["instance"] == "docker")["status"] == "unreachable"


async def test_healthy_rows_get_no_container_field():
    clients = {"sonarr": FakeArr(ok=True), "docker": FakeDockerHealth()}
    res = await stack_health(clients)
    assert "container" not in next(r for r in res if r["instance"] == "sonarr")
