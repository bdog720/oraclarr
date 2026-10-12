from .base import BaseClient

CLEANER_NAMES = ("queue_cleaner", "download_cleaner", "malware_blocker", "blacklist_sync",
                 "seeker")


class CleanuparrClient(BaseClient):
    """Cleanuparr REST with the account API key (X-Api-Key).

    Read-only. Never call /api/jobs/{id}/start|trigger, write to /api/configuration/*,
    or read /api/configuration/notification_providers, /api/configuration/{arr}/instances
    or /api/account/* (they hold tokens and arr API keys).
    """

    async def general(self) -> dict:
        return await self.get_json("/api/configuration/general")

    async def cleaner_config(self, name: str) -> dict:
        if name not in CLEANER_NAMES:
            raise ValueError(f"unknown cleaner {name!r}")
        return await self.get_json(f"/api/configuration/{name}")

    async def download_clients(self) -> list[dict]:
        data = await self.get_json("/api/configuration/download_client")
        return (data.get("clients") if isinstance(data, dict) else data) or []

    async def seeding_rules(self, client_id: str) -> list[dict]:
        return await self.get_json(f"/api/seeding-rules/{client_id}")

    async def unlinked_config(self, client_id: str) -> dict:
        return await self.get_json(f"/api/unlinked-config/{client_id}")

    async def stall_rules(self) -> list[dict]:
        return await self.get_json("/api/queue-rules/stall")

    async def slow_rules(self) -> list[dict]:
        return await self.get_json("/api/queue-rules/slow")

    async def jobs(self) -> list[dict]:
        return await self.get_json("/api/jobs")

    async def strikes(self, page_size: int) -> tuple[list[dict], int]:
        data = await self.get_json("/api/strikes", params={"page": 1, "pageSize": page_size})
        return data.get("items") or [], data.get("totalCount") or 0

    async def recent_strikes(self) -> list[dict]:
        return await self.get_json("/api/strikes/recent")
