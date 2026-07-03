"""Shared interactive components."""

from collections.abc import Awaitable, Callable

import discord

from .music.track import Track
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
