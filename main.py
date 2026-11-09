
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing!")

intents = discord.Intents.default()

intents.members = True
intents.message_content = True


class NexusBot(commands.Bot):
    async def setup_hook(self):
        print("Loading extensions...")

        await self.load_extension("commands.economy")
        print("Loaded: economy")

        await self.load_extension("commands.moderation")
        print("Loaded: moderation")

        await self.load_extension("commands.kingdom")
        print("Loaded: kingdom")

        await self.tree.sync()

        print("Slash commands synced.")


bot = NexusBot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print("-" * 40)
    print(f"Logged in as: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Guilds: {len(bot.guilds)}")
    print("NEXUS RPG is online!")
    print("-" * 40)


@bot.event
async def on_disconnect():
    print("Bot disconnected from Discord Gateway.")


@bot.event
async def on_resumed():
    print("Discord Gateway connection resumed.")


bot.run(TOKEN)
