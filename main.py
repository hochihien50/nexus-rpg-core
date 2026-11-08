
import os
import traceback
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


class NexusBot(commands.Bot):
    async def setup_hook(self):
        print("[START] Dang khoi tao database...", flush=True)
        database.init_db()
        print("[START] Database OK", flush=True)

        await self.load_extension("commands.economy")
        print("[START] Loaded economy", flush=True)

        await self.load_extension("commands.moderation")
        print("[START] Loaded moderation", flush=True)

        synced = await self.tree.sync()
        print(f"[START] Da dong bo {len(synced)} slash commands.", flush=True)


intents = discord.Intents.default()
bot = NexusBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}", flush=True)
    print("NEXUS RPG is ready!", flush=True)


@bot.listen("on_interaction")
async def debug_interaction(interaction):
    if interaction.type == discord.InteractionType.application_command:
        name = interaction.data.get("name") if interaction.data else None

        print(
            f"[INTERACTION] name={name} "
            f"user={interaction.user} "
            f"id={interaction.id}",
            flush=True
        )


@bot.tree.error
async def on_app_command_error(interaction, error):
    print(
        f"[COMMAND ERROR] {interaction.command} : {repr(error)}",
        flush=True
    )

    traceback.print_exception(
        type(error),
        error,
        error.__traceback__
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                "Lenh gap loi. Hay kiem tra log bot.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Lenh gap loi. Hay kiem tra log bot.",
                ephemeral=True
            )
    except Exception as e:
        print(f"[ERROR] Khong the gui error response: {repr(e)}", flush=True)


if not TOKEN:
    raise RuntimeError("Thieu DISCORD_TOKEN trong Environment")

bot.run(TOKEN)
