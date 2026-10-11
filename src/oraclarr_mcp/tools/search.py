from ..clients.base import BaseClient
from ._arr import arr_clients, media_kind
from ._util import Bounded, bounded, clamp, fan_out

MAX_LIMIT = 200


def _item(i: dict) -> dict:
    stats = i.get("statistics") or {}
    return {
        "title": i.get("title"),
        "year": i.get("year"),
        "tvdb_id": i.get("tvdbId"),
        "tmdb_id": i.get("tmdbId"),
        "imdb_id": i.get("imdbId"),
        "monitored": i.get("monitored"),
        "status": i.get("status"),
        "path": i.get("path"),
        # Sonarr keeps size in statistics; Radarr has it on the movie.
        "size_on_disk": i.get("sizeOnDisk", stats.get("sizeOnDisk")),
        "episode_file_count": stats.get("episodeFileCount"),
        "episode_count": stats.get("episodeCount"),
        "has_file": i.get("hasFile"),
    }


async def search_media(clients: dict[str, BaseClient], term: str,
                       limit: int = 20) -> list[dict]:
    limit = clamp(limit, MAX_LIMIT)

    async def collect(c: BaseClient) -> Bounded:
        items = await c.lookup_library(term, media_kind(c))
        return bounded([_item(i) for i in items], limit)

    return await fan_out(arr_clients(clients, None), collect)
