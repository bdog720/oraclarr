import time
from typing import Callable

from .base import BaseClient

CACHE_TTL_S = 30


class NetdataClient(BaseClient):
    """Netdata v2 (no auth). Each read is the 10-second average of one context."""

    def __init__(self, *args, clock: Callable[[], float] = time.monotonic, **kwargs):
        super().__init__(*args, **kwargs)
        self._clock = clock
        self._cache: dict[str, tuple[float, list[dict[str, float]]]] = {}

    async def _instances(self, context: str) -> list[dict[str, float]]:
        now = self._clock()
        hit = self._cache.get(context)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
        data = await self.get_json("/api/v2/data", params={
            "contexts": context, "scope_contexts": context, "after": -10, "points": 1,
            "time_group": "average", "group_by": "instance,dimension", "format": "json2"})
        res = data.get("result") or {}
        labels = res.get("labels") or []
        rows = res.get("data") or []
        by_instance: dict[str, dict[str, float]] = {}
        if rows:
            # Labels look like "<dimension>,<chart>@<node>"; cells are [value, anomaly, flags].
            for label, cell in zip(labels[1:], rows[0][1:]):
                dimension, _, instance = label.partition(",")
                value = cell[0] if isinstance(cell, list) else cell
                if value is None:  # a gap in collection: leave the dimension out
                    continue
                by_instance.setdefault(instance, {})[dimension] = value
        out = [by_instance[k] for k in sorted(by_instance)]
        self._cache[context] = (now, out)
        return out

    async def latest(self, context: str) -> dict[str, float]:
        instances = await self._instances(context)
        return instances[0] if instances else {}

    async def latest_by_instance(self, context: str) -> list[dict[str, float]]:
        return await self._instances(context)

    async def info(self) -> dict:
        return await self.get_json("/api/v1/info")
