import logging
from typing import Any, Protocol
import httpx

log = logging.getLogger("oraclarr_mcp.client")

class AuthStrategy(Protocol):
    def headers(self) -> dict[str, str]: ...
    async def before_request(self, client: "BaseClient") -> None: ...
    async def on_auth_failure(self, client: "BaseClient") -> bool: ...  # True if retry

class NoAuth:
    def headers(self) -> dict[str, str]: return {}
    async def before_request(self, client): pass
    async def on_auth_failure(self, client): return False

class ApiKeyHeaderAuth:
    def __init__(self, key: str): self._key = key
    def headers(self) -> dict[str, str]: return {"X-Api-Key": self._key}
    async def before_request(self, client): pass
    async def on_auth_failure(self, client): return False

class BearerAuth:
    def __init__(self, token: str): self._token = token
    def headers(self) -> dict[str, str]: return {"Authorization": f"Bearer {self._token}"}
    async def before_request(self, client): pass
    async def on_auth_failure(self, client): return False

class BaseClient:
    def __init__(self, name: str, type: str, base_url: str, auth: AuthStrategy, timeout: int):
        self.name = name
        self.type = type
        self.auth = auth
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def get_json(self, path: str, params: dict | None = None) -> Any:
        await self.auth.before_request(self)
        resp = await self._request("GET", path, params=params)
        if resp.status_code in (401, 403) and await self.auth.on_auth_failure(self):
            resp = await self._request("GET", path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def post_json(self, path: str, json: Any = None, params: dict | None = None) -> Any:
        await self.auth.before_request(self)
        resp = await self._request("POST", path, json=json, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        log.debug("call %s %s %s", self.name, method, path)
        return await self._http.request(method, path, headers=self.auth.headers(), **kw)

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    async def aclose(self) -> None:
        await self._http.aclose()
