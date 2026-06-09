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
