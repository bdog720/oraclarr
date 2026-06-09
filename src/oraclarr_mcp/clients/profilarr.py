from .base import BaseClient


class ProfilarrClient(BaseClient):
    """Profilarr public REST API (v1). Profiles/custom-formats are not exposed
    per-arr; sync state lives in /api/v1/status (databases + per-arr sync)."""

    async def arr_instances(self) -> list[dict]:
        return await self.get_json("/api/v1/arr")

    async def status(self) -> dict:
        return await self.get_json("/api/v1/status")
