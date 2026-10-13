"""Two-step writes: a dry run stores a plan; only that plan_id can run it, once."""
import secrets
import time
from dataclasses import dataclass
from typing import Callable

PLAN_TTL_S = 600
MAX_PLANS = 100


@dataclass
class Plan:
    tool: str
    instance: str
    action: str
    args: dict
    request: dict
    preview: dict
    fingerprint: str
    target: dict | None = None
    plan_id: str = ""
    created: float = 0.0


class PlanStore:
    def __init__(self, ttl_s: float = PLAN_TTL_S, max_plans: int = MAX_PLANS,
                 clock: Callable[[], float] = time.monotonic):
        self._ttl, self._max, self._clock = ttl_s, max_plans, clock
        self._plans: dict[str, Plan] = {}  # insertion order = age

    def add(self, plan: Plan) -> str:
        now = self._clock()
        for k in [k for k, p in self._plans.items() if now - p.created >= self._ttl]:
            del self._plans[k]
        while len(self._plans) >= self._max:
            del self._plans[next(iter(self._plans))]
        plan.plan_id, plan.created = secrets.token_urlsafe(12), now
        self._plans[plan.plan_id] = plan
        return plan.plan_id

    def take(self, plan_id: str) -> Plan | None:
        # Synchronous on purpose: no await between lookup and removal, so two concurrent
        # calls with the same plan_id cannot both get it.
        plan = self._plans.pop(plan_id, None)
        if plan is None or self._clock() - plan.created >= self._ttl:
            return None
        return plan
