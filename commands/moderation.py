
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="nuke", description="Timeout mot thanh vien trong 60 giay")
    @app_commands.describe(member="Thanh vien can timeout")
    @app_commands.checks.cooldown(1, 10.0)
    async def nuke(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                "Lenh nay chi dung duoc trong server.",
                ephemeral=True
            )
            return

        if not interaction.user.guild_permissions.moderate_members:
            await interaction.followup.send(
                "Ban can quyen Moderate Members de dung lenh nay.",
                ephemeral=True
            )
            return

        if member.id == interaction.guild.owner_id:
            await interaction.followup.send(
                "Khong the nuke chu server.",
                ephemeral=True
            )
            return

        if member.id == interaction.user.id:
            await interaction.followup.send(
                "Ban khong the tu nuke minh.",
                ephemeral=True
            )
            return

        bot_member = interaction.guild.me

        if bot_member is None or member.top_role >= bot_member.top_role:
            await interaction.followup.send(
                "Role cao nhat cua bot phai cao hon role cua muc tieu.",
                ephemeral=True
            )
            return

        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(
                "Ban khong the nuke nguoi co role bang hoac cao hon ban.",
                ephemeral=True
            )
            return

        try:
            await member.timeout(
                discord.utils.utcnow() + timedelta(seconds=60),
                reason="Nuke command"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Bot khong du quyen timeout thanh vien nay.",
                ephemeral=True
            )
            return
        except discord.HTTPException as e:
            print(f"Loi nuke HTTP: {e}")
            await interaction.followup.send(
                "Discord khong the thuc hien timeout luc nay.",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"NUKED! {member.mention} da bi timeout trong 60 giay.",
            ephemeral=True
        )

    @nuke.error
    async def nuke_error(self, interaction: discord.Interaction, error):
        print(f"Loi command nuke: {error}")

        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"Thu lai sau {error.retry_after:.1f} giay."
        else:
            message = "Lenh khong the thuc hien. Hay kiem tra log."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
