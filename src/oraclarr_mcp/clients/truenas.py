import asyncio
import json
import ssl
import time
from typing import Any, Awaitable, Callable

CACHE_TTL_S = 30
_MAX_FRAME = 16 * 2**20
_REASON_MAX = 300
POOL_FIELDS = ["name", "status", "healthy", "size", "allocated", "free", "fragmentation", "scan"]
DATASET_FIELDS = ["id", "used", "available", "quota", "refquota", "pool"]


class TruenasAuthError(Exception):
    pass


class TruenasCallError(Exception):
    pass


class TruenasConnectError(Exception):
    pass


def ws_url(url: str) -> str:
    base = url.rstrip("/")
    if not base.lower().startswith("https://"):
        raise ValueError("TrueNAS URL must use https://")
    return "wss://" + base[len("https://"):] + "/api/current"


def _ssl_context(verify: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _default_connect(uri: str, ssl_ctx: ssl.SSLContext, timeout: float):
    from websockets.asyncio.client import connect
    return connect(uri, ssl=ssl_ctx, open_timeout=timeout, max_size=_MAX_FRAME)


class TruenasClient:
    """TrueNAS 25.10 JSON-RPC 2.0 over WebSocket (REST refuses API keys).

    Read-only: only the query methods below are ever called. Each batch opens a
    connection, logs in with the API key, runs the calls and closes. Error replies carry
    a server traceback with locals; only message and reason are kept.
    """

    def __init__(self, name: str, type: str, url: str, api_key: str, timeout: float,
                 verify_tls: bool = True, connect: Callable | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.name = name
        self.type = type
        self._uri = ws_url(url)
        self._key = api_key
        self._timeout = timeout
        self._ssl = _ssl_context(verify_tls)
        self._connect = connect or _default_connect
        self._clock = clock
        self._cache: dict[str, tuple[float, Any]] = {}

    async def aclose(self) -> None:
        pass

    async def call_many(self, calls: list[tuple[str, list]]) -> list[Any]:
        try:
            async with self._connect(self._uri, self._ssl, self._timeout) as ws:
                try:
                    ok = await self._rpc(ws, 1, "auth.login_with_api_key", [self._key])
                except TruenasCallError as e:
                    raise TruenasAuthError(str(e)) from None
                if ok is not True:
                    raise TruenasAuthError("TrueNAS rejected the API key")
                return [await self._rpc(ws, i, m, p) for i, (m, p) in enumerate(calls, 2)]
        except ssl.SSLCertVerificationError:
            from ..config import env_name
            raise TruenasConnectError(
                f"TLS certificate check failed for {self.name}; set "
                f"{env_name(self.name, 'VERIFY_TLS')}=false for a self-signed certificate"
            ) from None

    async def _rpc(self, ws, rid: int, method: str, params: list) -> Any:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                                  "params": params}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), self._timeout))
            if msg.get("id") != rid:
                continue  # event notifications and stray replies
            if "error" in msg:
                err = msg.get("error") or {}
                reason = str((err.get("data") or {}).get("reason") or "")[:_REASON_MAX]
                raise TruenasCallError(f"{method}: {err.get('message')}"
                                       + (f" ({reason})" if reason else ""))
            return msg.get("result")

    async def _cached(self, key: str, fetch: Callable[[], Awaitable[Any]]) -> Any:
        now = self._clock()
        hit = self._cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            return hit[1]
        value = await fetch()
        self._cache[key] = (now, value)
        return value

    async def _one(self, method: str, params: list) -> Any:
        return (await self.call_many([(method, params)]))[0]

    async def system_info(self) -> dict:
        return await self._cached("system_info", lambda: self._one("system.info", []))

    async def pools(self) -> list[dict]:
        return await self._cached("pools", lambda: self._one(
            "pool.query", [[], {"select": POOL_FIELDS}]))

    async def datasets(self) -> list[dict]:
        return await self._cached("datasets", lambda: self._one(
            "pool.dataset.query", [[["type", "=", "FILESYSTEM"]], {
                "select": DATASET_FIELDS, "extra": {"flat": True, "retrieve_children": True}}]))

    async def alerts(self) -> list[dict]:
        return await self._cached("alerts", lambda: self._one("alert.list", []))

    async def disk_temps(self) -> list[dict]:
        async def fetch() -> list[dict]:
            graphs = await self._one("reporting.netdata_graphs", [])
            ids = next((g.get("identifiers") or [] for g in graphs
                        if g.get("name") == "disktemp"), [])
            if not ids:
                return []
            now = int(time.time())
            data = await self._one("reporting.netdata_get_data", [
                [{"name": "disktemp", "identifier": i} for i in ids],
                {"start": now - 120, "end": now, "aggregate": True}])
            out = []
            for g in data or []:
                rows = g.get("data") or []
                last = next((r[1] for r in reversed(rows) if len(r) > 1 and r[1] is not None),
                            None)
                out.append({"identifier": g.get("identifier"), "temp_c": last})
            return out
        return await self._cached("disk_temps", fetch)
