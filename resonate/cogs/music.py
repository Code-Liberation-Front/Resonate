"""Playback commands: search, play, and queue control."""

import dataclasses
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..music import extractor, resolver, ytmusic
from ..music.player import MusicPlayer
from ..music.track import Track
from ..utils import EMBED_COLOR, format_duration, respond, trim

log = logging.getLogger(__name__)

SEARCH_RESULTS = 8


class SearchSelect(discord.ui.Select["SearchView"]):
    def __init__(self, tracks: list[Track]) -> None:
        options = [
            discord.SelectOption(
                label=trim(track.title, 100),
                description=trim(f"{track.artists} • {track.duration_str}", 100),
                value=str(index),
            )
            for index, track in enumerate(tracks)
        ]
        super().__init__(placeholder="Pick a song to queue…", options=options)
        self.tracks = tracks

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if interaction.user.id != view.requester_id:
            await interaction.response.send_message(
                "Only the person who ran the search can pick a song.", ephemeral=True
            )
            return
        track = dataclasses.replace(
            self.tracks[int(self.values[0])], requested_by=interaction.user.id
        )
        await interaction.response.defer()
        vc = await view.cog.ensure_voice(interaction)
        if vc is None:
            return
        player = view.cog.get_player(interaction)
        await player.enqueue(track)
        view.stop()
        embed = discord.Embed(
            description=f"Queued **[{track.title}]({track.music_url})** — {track.artists}",
            color=EMBED_COLOR,
        )
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except discord.HTTPException:
            pass


class SearchView(discord.ui.View):
    def __init__(self, cog: "Music", requester_id: int, tracks: list[Track]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.requester_id = requester_id
        self.message: discord.Message | None = None
        self.add_item(SearchSelect(tracks))

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class Music(commands.Cog):
    """Search YouTube Music and play songs in voice channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}

    async def cog_unload(self) -> None:
        for player in list(self.players.values()):
            player.destroy()

    def get_player(self, interaction: discord.Interaction) -> MusicPlayer:
        player = self.players.get(interaction.guild_id)
        if player is None or player.closed:
            player = MusicPlayer(
                self.bot,
                interaction.guild,
                interaction.channel,
                idle_timeout=self.bot.config.idle_timeout,
                on_destroy=lambda guild_id: self.players.pop(guild_id, None),
            )
            self.players[interaction.guild_id] = player
        return player

    async def ensure_voice(
        self, interaction: discord.Interaction
    ) -> discord.VoiceClient | None:
        """Join the caller's voice channel, or explain why that's not possible."""
        voice = getattr(interaction.user, "voice", None)
        if voice is None or voice.channel is None:
            await respond(
                interaction, "You need to be in a voice channel first.", ephemeral=True
            )
            return None
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_connected():
            try:
                vc = await voice.channel.connect(self_deaf=True)
            except discord.ClientException:
                vc = interaction.guild.voice_client
                if vc is None:
                    raise
        elif vc.channel != voice.channel:
            if vc.is_playing() or vc.is_paused():
                await respond(
                    interaction,
                    f"I'm already playing music in {vc.channel.mention}.",
                    ephemeral=True,
                )
                return None
            await vc.move_to(voice.channel)
        return vc

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # Clean up if the bot is kicked or disconnected from voice.
        if member.id == self.bot.user.id and after.channel is None:
            player = self.players.pop(member.guild.id, None)
            if player is not None:
                player.destroy()

    @app_commands.command(description="Play a song from YouTube Music (song name or URL).")
    @app_commands.describe(query="Song name, artist, or a YouTube / YouTube Music URL")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        voice = getattr(interaction.user, "voice", None)
        if voice is None or voice.channel is None:
            await respond(
                interaction, "You need to be in a voice channel first.", ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            track = await resolver.resolve_track(query)
        except extractor.ExtractionError:
            await respond(interaction, f"Couldn't find anything for **{trim(query, 100)}**.")
            return
        track.requested_by = interaction.user.id
        if await self.ensure_voice(interaction) is None:
            return
        player = self.get_player(interaction)
        await player.enqueue(track)
        embed = discord.Embed(
            description=f"Queued **[{track.title}]({track.music_url})** — {track.artists}",
            color=EMBED_COLOR,
        )
        queued_behind = len(player.queue)
        if player.current is not None and queued_behind:
            embed.set_footer(text=f"Position in queue: {queued_behind}")
        await respond(interaction, embed=embed)

    @app_commands.command(description="Search YouTube Music and pick a song to queue.")
    @app_commands.describe(query="What to search for")
    @app_commands.guild_only()
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        try:
            tracks = await ytmusic.search_songs(query, limit=SEARCH_RESULTS)
        except Exception:
            log.exception("YouTube Music search failed")
            await respond(interaction, "Search failed — please try again in a moment.")
            return
        if not tracks:
            await respond(interaction, f"No results for **{trim(query, 100)}**.")
            return
        lines = [
            f"`{index}.` **{trim(track.title, 60)}** — {trim(track.artists, 60)} ({track.duration_str})"
            for index, track in enumerate(tracks, 1)
        ]
        embed = discord.Embed(
            title=f"Results for “{trim(query, 80)}”",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        view = SearchView(self, interaction.user.id, tracks)
        view.message = await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(description="Show what's playing and what's up next.")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None or (player.current is None and not len(player.queue)):
            await respond(interaction, "Nothing is queued right now.")
            return
        embed = discord.Embed(title="Queue", color=EMBED_COLOR)
        if player.current is not None:
            current = player.current
            embed.add_field(
                name="Now playing",
                value=f"[{trim(current.title, 60)}]({current.music_url}) — "
                f"{trim(current.artists, 60)} ({current.duration_str})",
                inline=False,
            )
        upcoming = list(player.queue)
        if upcoming:
            lines = [
                f"`{index}.` [{trim(track.title, 50)}]({track.music_url}) ({track.duration_str})"
                for index, track in enumerate(upcoming[:10], 1)
            ]
            if len(upcoming) > 10:
                lines.append(f"…and {len(upcoming) - 10} more")
            total = sum(track.duration for track in upcoming)
            embed.add_field(
                name=f"Up next — {len(upcoming)} track(s), {format_duration(total)}",
                value="\n".join(lines),
                inline=False,
            )
        await respond(interaction, embed=embed)

    @app_commands.command(description="Show the song that's playing right now.")
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None or player.current is None:
            await respond(interaction, "Nothing is playing right now.")
            return
        await respond(interaction, embed=player.now_playing_embed())

    @app_commands.command(description="Skip the current song.")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None or player.current is None:
            await respond(interaction, "Nothing is playing right now.")
            return
        title = player.current.title
        player.skip()
        await respond(interaction, f"⏭️ Skipped **{title}**.")

    @app_commands.command(description="Pause playback.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_playing():
            await respond(interaction, "Nothing is playing right now.")
            return
        vc.pause()
        await respond(interaction, "⏸️ Paused.")

    @app_commands.command(description="Resume playback.")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_paused():
            await respond(interaction, "Nothing is paused right now.")
            return
        vc.resume()
        await respond(interaction, "▶️ Resumed.")

    @app_commands.command(description="Stop playback and clear the queue.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None or (player.current is None and not len(player.queue)):
            await respond(interaction, "Nothing is playing right now.")
            return
        player.stop()
        await respond(interaction, "⏹️ Stopped and cleared the queue.")

    @app_commands.command(description="Shuffle the queue.")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None or len(player.queue) < 2:
            await respond(interaction, "There aren't enough queued tracks to shuffle.")
            return
        player.queue.shuffle()
        await respond(interaction, f"🔀 Shuffled {len(player.queue)} tracks.")

    @app_commands.command(description="Remove a track from the queue.")
    @app_commands.describe(position="Track number, as shown by /queue")
    @app_commands.guild_only()
    async def remove(
        self,
        interaction: discord.Interaction,
        position: app_commands.Range[int, 1],
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None or position > len(player.queue):
            await respond(interaction, "There's no track at that position.")
            return
        track = player.queue.remove(position - 1)
        await respond(interaction, f"🗑️ Removed **{track.title}** from the queue.")

    @app_commands.command(description="Set the playback volume.")
    @app_commands.describe(percent="Volume from 1 to 200 (100 = normal)")
    @app_commands.guild_only()
    async def volume(
        self,
        interaction: discord.Interaction,
        percent: app_commands.Range[int, 1, 200],
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if player is None:
            await respond(interaction, "I'm not playing anything right now.")
            return
        player.set_volume(percent / 100)
        await respond(interaction, f"🔊 Volume set to {percent}%.")

    @app_commands.command(description="Disconnect the bot from the voice channel.")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        player = self.players.pop(interaction.guild_id, None)
        vc = interaction.guild.voice_client
        if player is None and vc is None:
            await respond(interaction, "I'm not in a voice channel.")
            return
        if player is not None:
            player.destroy()
        elif vc is not None:
            await vc.disconnect(force=True)
        await respond(interaction, "👋 Disconnected.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
