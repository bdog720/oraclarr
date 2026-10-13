import asyncio

from oraclarr_mcp.plans import MAX_PLANS, PLAN_TTL_S, Plan, PlanStore


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _plan(n=0):
    return Plan(tool="start_job", instance="sonarr", action="refresh", args={"n": n},
                request={"method": "POST", "path": "/api/v3/command", "json": {"n": n}},
                preview={}, fingerprint=f"fp{n}")


def test_add_returns_unique_ids_and_take_is_single_use():
    s = PlanStore(clock=Clock())
    a, b = s.add(_plan(1)), s.add(_plan(2))
    assert a != b and len(a) >= 16
    assert s.take(a).args == {"n": 1}
    assert s.take(a) is None


def test_expired_plan_is_gone():
    clock = Clock()
    s = PlanStore(clock=clock)
    pid = s.add(_plan())
    clock.t += PLAN_TTL_S
    assert s.take(pid) is None


def test_cap_evicts_oldest_first():
    s = PlanStore(clock=Clock(), max_plans=3)
    ids = [s.add(_plan(i)) for i in range(4)]
    assert s.take(ids[0]) is None and s.take(ids[3]).args == {"n": 3}


def test_default_cap():
    s = PlanStore(clock=Clock())
    ids = [s.add(_plan(i)) for i in range(MAX_PLANS + 1)]
    assert s.take(ids[0]) is None and s.take(ids[-1]) is not None


async def test_concurrent_takes_have_one_winner():
    s = PlanStore(clock=Clock())
    pid = s.add(_plan())

    async def take():
        await asyncio.sleep(0)
        return s.take(pid)

    got = await asyncio.gather(*(take() for _ in range(5)))
    assert sum(p is not None for p in got) == 1
