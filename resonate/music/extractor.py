"""Resolve tracks and audio stream URLs with yt-dlp."""

import asyncio
import functools

import discord
import yt_dlp

from .track import Track


class ExtractionError(Exception):
    """Raised when yt-dlp cannot resolve a query or stream."""


_YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
}

_FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
_FFMPEG_OPTS = "-vn"

_ytdl = yt_dlp.YoutubeDL(_YTDL_OPTS)


async def _extract(query: str) -> dict:
    loop = asyncio.get_running_loop()
    try:
        info = await loop.run_in_executor(
            None, functools.partial(_ytdl.extract_info, query, download=False)
        )
    except yt_dlp.utils.DownloadError as exc:
        raise ExtractionError(str(exc)) from exc
    if info is None:
        raise ExtractionError("No results found.")
    if "entries" in info:
        entries = [entry for entry in info["entries"] if entry]
        if not entries:
            raise ExtractionError("No results found.")
        info = entries[0]
    return info


def _to_track(info: dict) -> Track:
    return Track(
        video_id=info.get("id") or "",
        title=info.get("title") or "Unknown title",
        artists=info.get("artist") or info.get("uploader") or "Unknown artist",
        duration=int(info.get("duration") or 0),
        thumbnail=info.get("thumbnail"),
    )


async def resolve(query: str) -> Track:
    """Resolve a URL or a yt-dlp search query to a single Track."""
    return _to_track(await _extract(query))


async def create_source(track: Track, volume: float) -> discord.PCMVolumeTransformer:
    """Fetch a fresh stream URL for a track and wrap it in an FFmpeg audio source.

    Stream URLs expire, so this must be called right before playback rather
    than when the track is queued.
    """
    info = await _extract(track.watch_url)
    stream_url = info.get("url")
    if not stream_url:
        raise ExtractionError("Could not get an audio stream for this track.")
    source = discord.FFmpegPCMAudio(
        stream_url, before_options=_FFMPEG_BEFORE, options=_FFMPEG_OPTS
    )
    return discord.PCMVolumeTransformer(source, volume=volume)
