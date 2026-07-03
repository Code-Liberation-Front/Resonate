"""Search YouTube Music via ytmusicapi (no authentication required)."""

import asyncio
import functools

from ytmusicapi import YTMusic

from .track import Track

_client: YTMusic | None = None


def _get_client() -> YTMusic:
    global _client
    if _client is None:
        _client = YTMusic()
    return _client


def _search_blocking(query: str, limit: int) -> list[dict]:
    return _get_client().search(query, filter="songs", limit=limit)


async def search_songs(query: str, limit: int = 10) -> list[Track]:
    """Search YouTube Music for songs matching a free-text query."""
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, functools.partial(_search_blocking, query, limit)
    )
    tracks: list[Track] = []
    for item in results:
        video_id = item.get("videoId")
        if not video_id:
            continue
        artists = ", ".join(
            artist["name"]
            for artist in item.get("artists") or []
            if artist.get("name")
        )
        thumbnails = item.get("thumbnails") or []
        tracks.append(
            Track(
                video_id=video_id,
                title=item.get("title") or "Unknown title",
                artists=artists or "Unknown artist",
                duration=item.get("duration_seconds") or 0,
                thumbnail=thumbnails[-1]["url"] if thumbnails else None,
            )
        )
        if len(tracks) >= limit:
            break
    return tracks
