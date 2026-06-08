from .base import BaseClient


class ProfilarrClient(BaseClient):
    async def arr_instances(self) -> list[dict]:
        return await self.get_json("/api/arr")

    async def quality_profiles(self, arr_id: int) -> list[dict]:
        return await self.get_json(f"/api/arr/{arr_id}/quality-profiles")

    async def custom_formats(self, arr_id: int) -> list[dict]:
        return await self.get_json(f"/api/arr/{arr_id}/custom-formats")
