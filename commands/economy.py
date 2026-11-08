
import asyncio
from datetime import datetime, timedelta, timezone
import random
import discord
from discord import app_commands
from discord.ext import commands

import database


def now_utc():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Xem ho so nhan vat")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            player = await asyncio.to_thread(
                database.ensure_player,
                interaction.user.id,
                interaction.user.name
            )

            embed = discord.Embed(
                title=f"Adventurer: {player['username']}",
                color=discord.Color.blurple()
            )

            embed.add_field(name="Level", value=player["level"])
            embed.add_field(name="EXP", value=player["exp"])
            embed.add_field(name="HP", value=player["hp"])
            embed.add_field(name="Gold", value=f"{player['gold']:,}")
            embed.add_field(name="Gems", value=f"{player['gems']:,}")

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] profile: {repr(e)}", flush=True)
            await interaction.followup.send(
                "Khong the tai ho so. Hay kiem tra database.",
                ephemeral=True
            )

    @app_commands.command(name="balance", description="Xem so du")
    async def balance(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            player = await asyncio.to_thread(
                database.ensure_player,
                interaction.user.id,
                interaction.user.name
            )

            await interaction.followup.send(
                f"**{interaction.user.display_name}**: "
                f"{player['gold']:,} Gold | {player['gems']:,} Gems",
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] balance: {repr(e)}", flush=True)
            await interaction.followup.send(
                "Khong the tai so du. Hay kiem tra database.",
                ephemeral=True
            )

    @app_commands.command(name="daily", description="Nhan thuong hang ngay")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            player = await asyncio.to_thread(
                database.ensure_player,
                interaction.user.id,
                interaction.user.name
            )

            now = now_utc()
            last = parse_time(player["daily_at"])

            if last and now - last < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)

                await interaction.followup.send(
                    f"Ban da nhan daily roi. Thu lai sau {hours}h {minutes}m.",
                    ephemeral=True
                )
                return

            reward = random.randint(100, 250)

            await asyncio.to_thread(
                database.update_player,
                interaction.user.id,
                gold=player["gold"] + reward,
                daily_at=now.isoformat()
            )

            await interaction.followup.send(
                f"🎁 Ban nhan duoc **{reward:,} Gold**!",
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] daily: {repr(e)}", flush=True)
            await interaction.followup.send(
                "Khong the nhan daily. Hay kiem tra database.",
                ephemeral=True
            )

    @app_commands.command(name="work", description="Lam viec kiem Gold")
    async def work(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            player = await asyncio.to_thread(
                database.ensure_player,
                interaction.user.id,
                interaction.user.name
            )

            now = now_utc()
            last = parse_time(player["work_at"])

            if last and now - last < timedelta(minutes=5):
                remaining = timedelta(minutes=5) - (now - last)
                seconds = int(remaining.total_seconds())

                await interaction.followup.send(
                    f"Hay nghi mot chut. Thu lai sau "
                    f"{seconds // 60}p {seconds % 60}s.",
                    ephemeral=True
                )
                return

            reward = random.randint(25, 80)

            await asyncio.to_thread(
                database.update_player,
                interaction.user.id,
                gold=player["gold"] + reward,
                work_at=now.isoformat()
            )

            await interaction.followup.send(
                f"💼 Ban lam viec va kiem duoc **{reward} Gold**!",
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] work: {repr(e)}", flush=True)
            await interaction.followup.send(
                "Khong the work. Hay kiem tra database.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Economy(bot))
