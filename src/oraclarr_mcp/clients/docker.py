import asyncio
import time
from typing import Any, Awaitable, Callable

import httpx

from .base import BaseClient

CACHE_TTL_S = 30
INSPECT_CONCURRENCY = 8
COMPOSE_LABELS = ("com.docker.compose.project", "com.docker.compose.service")


class DockerProxyRefused(Exception):
    pass


def demux(raw: bytes, tty: bool) -> list[tuple[str, str]]:
    """Docker log bytes -> (stream, line). Non-TTY logs are 8-byte-header frames:
    byte 0 = stream (1 stdout, 2 stderr), bytes 4-7 = big-endian payload length."""
    def text(b: bytes) -> str:
        return b.decode("utf-8", "replace").rstrip("\r")

    if tty:
        return [("stdout", text(line)) for line in raw.split(b"\n") if line]
    out: list[tuple[str, str]] = []
    pending = {"stdout": b"", "stderr": b""}
    i = 0
    while i + 8 <= len(raw):
        stream = "stderr" if raw[i] == 2 else "stdout"
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        chunk = pending[stream] + raw[i + 8:i + 8 + size]
        i += 8 + size
        *done, pending[stream] = chunk.split(b"\n")
        out += [(stream, text(line)) for line in done]
    out += [(stream, text(rest)) for stream, rest in pending.items() if rest]
    return out


def _compose(labels: dict | None) -> dict:
    return {k: v for k, v in (labels or {}).items() if k in COMPOSE_LABELS}


def slim_listing(x: dict) -> dict:
    """Allowlist one /containers/json row: no Mounts, Command or other labels."""
    return {"Id": x.get("Id"), "Names": x.get("Names") or [], "Image": x.get("Image"),
            "State": x.get("State"), "Status": x.get("Status"),
            "Ports": [{"PublicPort": p.get("PublicPort")} for p in x.get("Ports") or []],
            "Labels": _compose(x.get("Labels")),
            "HostConfig": {"NetworkMode": (x.get("HostConfig") or {}).get("NetworkMode")}}


def slim_inspect(d: dict) -> dict:
    """Allowlist an inspect result. Config.Env holds every service's secrets: never kept."""
    cfg, host = d.get("Config") or {}, d.get("HostConfig") or {}
    return {"Id": d.get("Id"), "Name": d.get("Name"), "RestartCount": d.get("RestartCount"),
            "State": d.get("State") or {},
            "Config": {"Image": cfg.get("Image"), "Tty": cfg.get("Tty")},
            "HostConfig": {"NetworkMode": host.get("NetworkMode"),
                           "RestartPolicy": host.get("RestartPolicy")}}


class DockerClient(BaseClient):
    """Docker Engine API through a read-only socket proxy (GET allowlist). GET only."""

    def __init__(self, *args, clock: Callable[[], float] = time.monotonic, **kwargs):
        super().__init__(*args, **kwargs)
        self._clock = clock
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        resp = await self._request("GET", path, params=params)
        if resp.status_code == 403:
            raise DockerProxyRefused(
                f"the docker proxy refused GET {path}: check -allowGET and -allowfrom")
        return resp

    async def _json(self, path: str, params: dict | None = None) -> Any:
        resp = await self._get(path, params)
        resp.raise_for_status()
        return resp.json()

    async def _cached(self, key: str, fetch: Callable[[], Awaitable[Any]]) -> Any:
        now = self._clock()
        hit = self._cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
        value = await fetch()
        # Drop expired entries: recreated containers get new IDs.
        self._cache = {k: v for k, v in self._cache.items() if now - v[0] < CACHE_TTL_S}
        self._cache[key] = (now, value)
        return value

    async def version(self) -> dict:
        return await self._json("/version")

    async def containers(self) -> list[dict]:
        async def fetch() -> list[dict]:
            return [slim_listing(x) for x in await self._json("/containers/json", {"all": 1})]
        return await self._cached("containers", fetch)

    async def inspect(self, cid: str) -> dict | None:
        async def fetch() -> dict | None:
            resp = await self._get(f"/containers/{cid}/json")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return slim_inspect(resp.json())
        return await self._cached(f"inspect:{cid}", fetch)

    async def inspect_many(self, ids: list[str]) -> list[dict | None]:
        sem = asyncio.Semaphore(INSPECT_CONCURRENCY)

        async def one(cid: str) -> dict | None:
            async with sem:
                return await self.inspect(cid)
        return list(await asyncio.gather(*(one(i) for i in ids)))

    async def logs(self, cid: str, tail: int, since: int | None = None) -> bytes:
        params: dict[str, Any] = {"stdout": 1, "stderr": 1, "timestamps": 1, "tail": tail}
        if since is not None:
            params["since"] = since
        resp = await self._get(f"/containers/{cid}/logs", params)
        resp.raise_for_status()
        return resp.content
