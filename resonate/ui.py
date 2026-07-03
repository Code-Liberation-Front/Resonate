"""Shared interactive components."""

from collections.abc import Awaitable, Callable

import aiosqlite
import discord

from .music.track import Track
from .storage.database import MAX_TRACKS_PER_PLAYLIST, Database
from .utils import EMBED_COLOR, trim

# Receives the button click's interaction (already deferred) and the chosen
# track. Returns the embed that replaces the picker message, or None if the
# pick was rejected (after answering ephemerally) so the picker stays usable.
PickHandler = Callable[[discord.Interaction, Track], Awaitable[discord.Embed | None]]


def results_embed(query: str, tracks: list[Track]) -> discord.Embed:
    lines = [
        f"`{index}.` **{trim(track.title, 60)}** — {trim(track.artists, 60)} ({track.duration_str})"
        for index, track in enumerate(tracks, 1)
    ]
    embed = discord.Embed(
        title=f"Results for “{trim(query, 80)}”",
        description="\n".join(lines),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Click a number to pick a song.")
    return embed


class TrackPickerView(discord.ui.View):
    """Numbered buttons matching a results list, one per track."""

    def __init__(
        self,
        requester_id: int,
        tracks: list[Track],
        on_pick: PickHandler,
        *,
        timeout: float = 60,
    ) -> None:
        super().__init__(timeout=timeout)
        self.requester_id = requester_id
        self.on_pick = on_pick
        self.message: discord.Message | None = None
        self._picked = False
        for index, track in enumerate(tracks[:25]):
            self.add_item(_TrackButton(index, track))

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class NowPlayingView(discord.ui.View):
    """'Add to playlist' button under a now-playing message.

    Any listener can click it; each user then picks from their own playlists
    in an ephemeral message.
    """

    def __init__(self, db: Database, track: Track, *, timeout: float = 600) -> None:
        super().__init__(timeout=timeout)
        self.db = db
        self.track = track
        self.message: discord.Message | None = None

    @discord.ui.button(
        label="Add to playlist", emoji="➕", style=discord.ButtonStyle.secondary
    )
    async def add_to_playlist(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        playlists = await self.db.list_playlists(interaction.user.id)
        if not playlists:
            await interaction.response.send_message(
                "You don't have any playlists yet — create one with `/playlist create`.",
                ephemeral=True,
            )
            return
        picker = _PlaylistPickView(self.db, self.track, playlists)
        await interaction.response.send_message(
            f"Add **{trim(self.track.title, 100)}** to which playlist?",
            view=picker,
            ephemeral=True,
        )
        try:
            picker.message = await interaction.original_response()
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class _PlaylistPickView(discord.ui.View):
    """One button per playlist the clicking user owns."""

    def __init__(
        self, db: Database, track: Track, playlists: list[tuple[str, int]]
    ) -> None:
        super().__init__(timeout=60)
        self.db = db
        self.track = track
        self.message: discord.Message | None = None
        for name, _count in playlists[:25]:
            self.add_item(_PlaylistButton(name))

    async def add_to(self, interaction: discord.Interaction, name: str) -> None:
        playlist_id = await self.db.get_playlist_id(interaction.user.id, name)
        if playlist_id is None:
            content = f"**{name}** no longer exists."
        elif await self.db.count_tracks(playlist_id) >= MAX_TRACKS_PER_PLAYLIST:
            content = f"**{name}** is full ({MAX_TRACKS_PER_PLAYLIST} tracks)."
        else:
            try:
                position = await self.db.add_track(playlist_id, self.track)
            except aiosqlite.IntegrityError:
                content = f"**{name}** no longer exists."
            else:
                content = (
                    f"➕ Added **{trim(self.track.title, 100)}** to **{name}** "
                    f"(track {position})."
                )
        self.stop()
        await interaction.response.edit_message(content=content, view=None)

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class _PlaylistButton(discord.ui.Button["_PlaylistPickView"]):
    def __init__(self, name: str) -> None:
        super().__init__(style=discord.ButtonStyle.secondary, label=trim(name, 40))
        self.playlist_name = name

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.add_to(interaction, self.playlist_name)


class _TrackButton(discord.ui.Button[TrackPickerView]):
    def __init__(self, index: int, track: Track) -> None:
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=str(index + 1),
            row=index // 5,
        )
        self.track = track

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if interaction.user.id != view.requester_id:
            await interaction.response.send_message(
                "Only the person who ran the command can pick.", ephemeral=True
            )
            return
        await interaction.response.defer()
        if view._picked:
            return
        view._picked = True
        embed = await view.on_pick(interaction, self.track)
        if embed is None:
            view._picked = False
            return
        view.stop()
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except discord.HTTPException:
            pass
