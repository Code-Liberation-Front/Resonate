import asyncio
import logging
from collections.abc import Callable, Iterable

import discord

from ..ui import NowPlayingView
from ..utils import EMBED_COLOR
from . import extractor
from .queue import TrackQueue
from .track import Track

log = logging.getLogger(__name__)


class MusicPlayer:
    """Per-guild playback state: a queue and a loop that feeds the voice client."""

    def __init__(
        self,
        bot,
        guild: discord.Guild,
        text_channel: discord.abc.Messageable,
        *,
        idle_timeout: int = 300,
        on_destroy: Callable[[int], None] | None = None,
    ) -> None:
        self.bot = bot
        self.guild = guild
        self.text_channel = text_channel
        self.queue = TrackQueue()
        self.current: Track | None = None
        self.volume = 0.5
        self.idle_timeout = idle_timeout
        self._on_destroy = on_destroy
        self._next = asyncio.Event()
        self._source: discord.PCMVolumeTransformer | None = None
        self._task = asyncio.create_task(self._player_loop())

    @property
    def voice_client(self) -> discord.VoiceClient | None:
        return self.guild.voice_client

    @property
    def closed(self) -> bool:
        return self._task.done()

    async def enqueue(self, track: Track) -> None:
        await self.queue.put(track)

    async def enqueue_many(self, tracks: Iterable[Track]) -> None:
        await self.queue.put_many(tracks)

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        if self._source is not None:
            self._source.volume = volume

    def skip(self) -> None:
        vc = self.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    def stop(self) -> None:
        self.queue.clear()
        self.skip()

    def destroy(self) -> None:
        """Tear the player down; cleanup happens in the loop's finally block."""
        self._task.cancel()

    async def _player_loop(self) -> None:
        try:
            while True:
                self._next.clear()
                self.current = None
                self._source = None
                try:
                    track = await asyncio.wait_for(
                        self.queue.get(), timeout=self.idle_timeout
                    )
                except asyncio.TimeoutError:
                    minutes = max(1, self.idle_timeout // 60)
                    await self._send(
                        f"Left the voice channel after {minutes} minute(s) of inactivity."
                    )
                    break

                vc = self.voice_client
                if vc is None or not vc.is_connected():
                    break

                try:
                    source = await extractor.create_source(track, self.volume)
                except extractor.ExtractionError as exc:
                    await self._send(f"⚠️ Skipping **{track.title}**: {exc}")
                    continue

                self.current = track
                self._source = source
                vc.play(source, after=self._playback_finished)
                view = NowPlayingView(
                    self.bot.db, track, timeout=max(600, (track.duration or 0) + 120)
                )
                view.message = await self._send(
                    embed=self.now_playing_embed(), view=view
                )
                await self._next.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Player loop crashed in guild %s", self.guild.id)
        finally:
            await self._cleanup()

    def _playback_finished(self, error: Exception | None) -> None:
        # Called from the voice thread, so hop back onto the event loop.
        if error:
            log.error("Playback error in guild %s: %s", self.guild.id, error)
        self.bot.loop.call_soon_threadsafe(self._next.set)

    async def _cleanup(self) -> None:
        self.queue.clear()
        self.current = None
        self._source = None
        if self._on_destroy is not None:
            self._on_destroy(self.guild.id)
        vc = self.guild.voice_client
        if vc is not None:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass

    async def _send(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> discord.Message | None:
        kwargs: dict = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view
        try:
            return await self.text_channel.send(**kwargs)
        except discord.HTTPException:
            log.warning("Could not send a message in guild %s", self.guild.id)
            return None

    def now_playing_embed(self) -> discord.Embed:
        track = self.current
        embed = discord.Embed(
            title="Now playing",
            description=f"**[{track.title}]({track.music_url})**\n{track.artists}",
            color=EMBED_COLOR,
        )
        embed.add_field(name="Duration", value=track.duration_str)
        if track.requested_by:
            embed.add_field(name="Requested by", value=f"<@{track.requested_by}>")
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        return embed
