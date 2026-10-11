from .base import BaseClient


class JellyfinClient(BaseClient):
    """Jellyfin 12.x REST. Read-only: never call POST /Library/Refresh here."""

    async def system_info(self) -> dict:
        return await self.get_json("/System/Info")

    async def virtual_folders(self) -> list[dict]:
        return await self.get_json("/Library/VirtualFolders")

    async def library_count(self, parent_id: str) -> int:
        data = await self.get_json("/Items", params={
            "parentId": parent_id, "recursive": "true", "limit": 0,
            "enableTotalRecordCount": "true"})
        return data.get("TotalRecordCount", 0)

    async def search_items(self, term: str, limit: int) -> tuple[list[dict], int]:
        data = await self.get_json("/Items", params={
            "searchTerm": term, "recursive": "true", "includeItemTypes": "Series,Movie",
            "fields": "ProviderIds,Path,DateCreated", "limit": limit,
            "enableTotalRecordCount": "true"})
        return data.get("Items", []), data.get("TotalRecordCount", 0)

    async def recent_items(self, limit: int) -> tuple[list[dict], int]:
        data = await self.get_json("/Items", params={
            "recursive": "true", "includeItemTypes": "Episode,Movie",
            "sortBy": "DateCreated", "sortOrder": "Descending", "fields": "DateCreated",
            "limit": limit, "enableTotalRecordCount": "true"})
        return data.get("Items", []), data.get("TotalRecordCount", 0)

    async def sessions(self) -> list[dict]:
        return await self.get_json("/Sessions", params={"activeWithinSeconds": 960})

    async def scheduled_tasks(self) -> list[dict]:
        return await self.get_json("/ScheduledTasks", params={"isHidden": "false"})
