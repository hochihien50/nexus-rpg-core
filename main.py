import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class NexusBot(commands.Bot):
    async def setup_hook(self):
        database.init_db()
        await self.load_extension("commands.economy")
        await self.load_extension("commands.moderation")
        synced = await self.tree.sync()
        print(f"Da dong bo {len(synced)} slash commands.")

intents = discord.Intents.default()
bot = NexusBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    print("NEXUS RPG is ready!")

if not TOKEN:
    raise RuntimeError("Thieu DISCORD_TOKEN trong file .env")

bot.run(TOKEN)
