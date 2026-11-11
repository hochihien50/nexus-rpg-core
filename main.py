
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

import database

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing!")


intents = discord.Intents.default()


class NexusBot(commands.Bot):
    async def setup_hook(self):
        print("=" * 45)
        print("NEXUS RPG - INITIALIZING")
        print("=" * 45)

        # Initialize database
        print("[DATABASE] Initializing...")
        await asyncio.to_thread(database.init_db)
        print("[DATABASE] Ready")

        # Load extensions
        extensions = [
            # Core systems
            "commands.economy",
            "commands.moderation",

            # Kingdom systems
            "commands.kingdom",
            "commands.kingdom_management",
            "commands.kingdom_achievements",
            "commands.kingdom_seasons",
            "commands.kingdom_leaderboard",

            # RPG systems
            "commands.gacha",
            "commands.inventory",
            "commands.weapons",
        ]

        for extension in extensions:
            try:
                await self.load_extension(extension)
                print(f"[LOADED] {extension}", flush=True)

            except Exception as error:
                print(
                    f"[FAILED] {extension}: {repr(error)}",
                    flush=True
                )
                raise

        # Sync slash commands
        print("[DISCORD] Syncing slash commands...")

        synced = await self.tree.sync()

        print(
            f"[DISCORD] Synced {len(synced)} slash commands",
            flush=True
        )

        print("=" * 45)
        print("NEXUS RPG INITIALIZATION COMPLETE")
        print("=" * 45)


bot = NexusBot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print("-" * 45)
    print(f"Logged in as: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Guilds: {len(bot.guilds)}")
    print("NEXUS RPG is online!")
    print("-" * 45)


@bot.event
async def on_disconnect():
    print("Bot disconnected from Discord Gateway.", flush=True)


@bot.event
async def on_resumed():
    print("Discord Gateway connection resumed.", flush=True)


bot.run(TOKEN)
