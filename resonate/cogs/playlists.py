"""Personal playlists: create, edit, and play them in any server."""

import dataclasses
import random

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from ..music import extractor, resolver
from ..music.track import Track
from ..ui import TrackPickerView, results_embed
from ..utils import EMBED_COLOR, format_duration, respond, trim
from .music import SEARCH_RESULTS

MAX_PLAYLISTS_PER_USER = 25
MAX_TRACKS_PER_PLAYLIST = 100

PlaylistName = app_commands.Range[str, 1, 60]


class Playlists(commands.Cog):
    """Create and play personal playlists (saved per user, usable in any server)."""

    playlist = app_commands.Group(
        name="playlist",
        description="Create and play your playlists",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def playlist_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        playlists = await self.bot.db.list_playlists(interaction.user.id)
        current = current.lower()
        return [
            app_commands.Choice(name=name, value=name)
            for name, _count in playlists
            if current in name.lower()
        ][:25]

    @playlist.command(name="create", description="Create a new playlist.")
    @app_commands.describe(name="A name for the playlist")
    async def create(self, interaction: discord.Interaction, name: PlaylistName) -> None:
        name = name.strip()
        if not name:
            await respond(interaction, "That name is empty.", ephemeral=True)
            return
        if await self.bot.db.count_playlists(interaction.user.id) >= MAX_PLAYLISTS_PER_USER:
            await respond(
                interaction,
                f"You already have {MAX_PLAYLISTS_PER_USER} playlists — delete one first.",
                ephemeral=True,
            )
            return
        if not await self.bot.db.create_playlist(interaction.user.id, name):
            await respond(
                interaction, f"You already have a playlist called **{name}**.", ephemeral=True
            )
            return
        await respond(
            interaction,
            f"🎶 Created playlist **{name}**. Add songs with `/playlist add`.",
        )

    @playlist.command(name="delete", description="Delete one of your playlists.")
    @app_commands.describe(name="The playlist to delete")
    @app_commands.autocomplete(name=playlist_name_autocomplete)
    async def delete(self, interaction: discord.Interaction, name: PlaylistName) -> None:
        if not await self.bot.db.delete_playlist(interaction.user.id, name):
            await respond(
                interaction, f"You don't have a playlist called **{name}**.", ephemeral=True
            )
            return
        await respond(interaction, f"🗑️ Deleted playlist **{name}**.")

    @playlist.command(name="list", description="List your playlists.")
    async def list_(self, interaction: discord.Interaction) -> None:
        playlists = await self.bot.db.list_playlists(interaction.user.id)
        if not playlists:
            await respond(
                interaction,
                "You don't have any playlists yet — create one with `/playlist create`.",
                ephemeral=True,
            )
            return
        lines = [
            f"• **{name}** — {count} track(s)" for name, count in playlists
        ]
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s playlists",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await respond(interaction, embed=embed)

    @playlist.command(name="show", description="Show the songs in a playlist.")
    @app_commands.describe(name="The playlist to show")
    @app_commands.autocomplete(name=playlist_name_autocomplete)
    async def show(self, interaction: discord.Interaction, name: PlaylistName) -> None:
        playlist_id = await self.bot.db.get_playlist_id(interaction.user.id, name)
        if playlist_id is None:
            await respond(
                interaction, f"You don't have a playlist called **{name}**.", ephemeral=True
            )
            return
        tracks = await self.bot.db.get_tracks(playlist_id)
        if not tracks:
            await respond(
                interaction,
                f"**{name}** is empty — add songs with `/playlist add`.",
            )
            return
        lines = [
            f"`{index}.` [{trim(track.title, 50)}]({track.music_url}) — "
            f"{trim(track.artists, 40)} ({track.duration_str})"
            for index, track in enumerate(tracks[:20], 1)
        ]
        if len(tracks) > 20:
            lines.append(f"…and {len(tracks) - 20} more")
        total = sum(track.duration for track in tracks)
        embed = discord.Embed(
            title=f"Playlist: {name}",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"{len(tracks)} track(s) • {format_duration(total)}")
        await respond(interaction, embed=embed)

    @playlist.command(name="add", description="Add a song to one of your playlists.")
    @app_commands.describe(
        name="The playlist to add to",
        query="Song name, artist, or a YouTube / YouTube Music URL",
    )
    @app_commands.autocomplete(name=playlist_name_autocomplete)
    async def add(
        self, interaction: discord.Interaction, name: PlaylistName, query: str
    ) -> None:
        playlist_id = await self.bot.db.get_playlist_id(interaction.user.id, name)
        if playlist_id is None:
            await respond(
                interaction, f"You don't have a playlist called **{name}**.", ephemeral=True
            )
            return
        if await self.bot.db.count_tracks(playlist_id) >= MAX_TRACKS_PER_PLAYLIST:
            await respond(
                interaction,
                f"**{name}** already has {MAX_TRACKS_PER_PLAYLIST} tracks.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        try:
            tracks = await resolver.search_or_resolve(query, limit=SEARCH_RESULTS)
        except extractor.ExtractionError:
            await respond(interaction, f"Couldn't find anything for **{trim(query, 100)}**.")
            return
        if len(tracks) == 1:
            await respond(
                interaction, embed=await self._added_embed(playlist_id, name, tracks[0])
            )
            return

        async def on_pick(_: discord.Interaction, track: Track) -> discord.Embed:
            return await self._added_embed(playlist_id, name, track)

        view = TrackPickerView(interaction.user.id, tracks, on_pick)
        view.message = await interaction.followup.send(
            embed=results_embed(query, tracks), view=view
        )

    async def _added_embed(
        self, playlist_id: int, name: str, track: Track
    ) -> discord.Embed:
        try:
            position = await self.bot.db.add_track(playlist_id, track)
        except aiosqlite.IntegrityError:
            return discord.Embed(
                description=f"**{name}** no longer exists.", color=EMBED_COLOR
            )
        return discord.Embed(
            description=f"➕ Added **[{track.title}]({track.music_url})** — {track.artists} "
            f"to **{name}** (track {position}).",
            color=EMBED_COLOR,
        )

    @playlist.command(name="remove", description="Remove a song from a playlist.")
    @app_commands.describe(
        name="The playlist to edit",
        position="Track number, as shown by /playlist show",
    )
    @app_commands.autocomplete(name=playlist_name_autocomplete)
    async def remove(
        self,
        interaction: discord.Interaction,
        name: PlaylistName,
        position: app_commands.Range[int, 1],
    ) -> None:
        playlist_id = await self.bot.db.get_playlist_id(interaction.user.id, name)
        if playlist_id is None:
            await respond(
                interaction, f"You don't have a playlist called **{name}**.", ephemeral=True
            )
            return
        track = await self.bot.db.remove_track(playlist_id, position)
        if track is None:
            await respond(interaction, "There's no track at that position.", ephemeral=True)
            return
        await respond(interaction, f"🗑️ Removed **{track.title}** from **{name}**.")

    @playlist.command(name="play", description="Queue every song in a playlist.")
    @app_commands.describe(
        name="The playlist to play",
        shuffle="Shuffle the playlist before queueing it",
    )
    @app_commands.autocomplete(name=playlist_name_autocomplete)
    async def play(
        self,
        interaction: discord.Interaction,
        name: PlaylistName,
        shuffle: bool = False,
    ) -> None:
        playlist_id = await self.bot.db.get_playlist_id(interaction.user.id, name)
        if playlist_id is None:
            await respond(
                interaction, f"You don't have a playlist called **{name}**.", ephemeral=True
            )
            return
        tracks = await self.bot.db.get_tracks(playlist_id)
        if not tracks:
            await respond(
                interaction, f"**{name}** is empty — add songs with `/playlist add`."
            )
            return
        music = self.bot.get_cog("Music")
        if music is None:
            await respond(interaction, "Playback is unavailable right now.", ephemeral=True)
            return
        await interaction.response.defer()
        if await music.ensure_voice(interaction) is None:
            return
        tracks = [
            dataclasses.replace(track, requested_by=interaction.user.id)
            for track in tracks
        ]
        if shuffle:
            random.shuffle(tracks)
        player = music.get_player(interaction)
        await player.enqueue_many(tracks)
        await respond(
            interaction,
            f"🎶 Queued {len(tracks)} track(s) from **{name}**"
            + (" (shuffled)." if shuffle else "."),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Playlists(bot))
