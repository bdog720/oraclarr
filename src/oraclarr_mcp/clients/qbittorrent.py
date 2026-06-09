from .base import BaseClient

class QbitCookieAuth:
    def __init__(self, username: str, password: str):
        self._u = username
        self._p = password
        self._logged_in = False

    def headers(self) -> dict[str, str]:
        return {}

    async def before_request(self, client: "QbitClient") -> None:
        if not self._logged_in:
            await self._login(client)

    async def on_auth_failure(self, client: "QbitClient") -> bool:
        self._logged_in = False
        await self._login(client)
        return True

    async def _login(self, client: "QbitClient") -> None:
        resp = await client.http.post(
            "/api/v2/auth/login",
            data={"username": self._u, "password": self._p},
            headers={"Referer": str(client.http.base_url)},
        )
        resp.raise_for_status()
        self._logged_in = True

class QbitClient(BaseClient):
    async def torrents(self) -> list[dict]:
        return await self.get_json("/api/v2/torrents/info")

    async def transfer_info(self) -> dict:
        return await self.get_json("/api/v2/transfer/info")
