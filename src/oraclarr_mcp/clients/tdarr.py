from .base import BaseClient


class TdarrClient(BaseClient):
    async def status(self) -> dict:
        return await self.get_json("/api/v2/status")

    async def nodes(self) -> dict:
        return await self.get_json("/api/v2/get-nodes")

    async def staged(self) -> list[dict]:
        # transcode queue / staged items via cruddb; confirm shape live
        data = await self.post_json("/api/v2/cruddb", json={
            "data": {"collection": "StagedJSONDB", "mode": "getAll"}})
        return data if isinstance(data, list) else data.get("array", [])
