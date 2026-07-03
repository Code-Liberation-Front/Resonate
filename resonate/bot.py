import logging

import discord
from discord import app_commands
from discord.ext import commands

from .config import Config
from .storage.database import Database

log = logging.getLogger(__name__)

EXTENSIONS = (
    "resonate.cogs.music",
    "resonate.cogs.playlists",
)


class Resonate(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self.db = Database(config.db_path)

    async def setup_hook(self) -> None:
        await self.db.connect()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        self.tree.on_error = self.on_app_command_error
        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Synced commands to guild %s", self.config.guild_id)
        else:
            await self.tree.sync()
            log.info("Synced global commands (new commands can take a while to appear)")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        command = interaction.command.qualified_name if interaction.command else "?"
        log.error("Command /%s failed", command, exc_info=error)
        message = "Something went wrong running that command."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    async def close(self) -> None:
        music = self.get_cog("Music")
        if music is not None:
            for player in list(music.players.values()):
                player.destroy()
        await self.db.close()
        await super().close()
