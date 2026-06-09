from .base import BaseClient

class ProwlarrClient(BaseClient):
    async def system_status(self) -> dict:
        return await self.get_json("/api/v1/system/status")

    async def health(self) -> list[dict]:
        return await self.get_json("/api/v1/health")

    async def indexers(self) -> list[dict]:
        return await self.get_json("/api/v1/indexer")

    async def indexer_stats(self) -> dict:
        return await self.get_json("/api/v1/indexerstats")
