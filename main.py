import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class NexusBot(commands.Bot):
    async def setup_hook(self):
        await self.load_extension("commands.economy")
        await self.load_extension("commands.moderation")
        await self.load_extension("commands.kingdom")

        await self.tree.sync()
        print("Slash commands synced.")


bot = NexusBot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


bot.run(TOKEN)
