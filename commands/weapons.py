import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import database


RARITY_NAMES = {
    1: "Common",
    2: "Uncommon",
    3: "Rare",
    4: "Epic",
    5: "Legendary"
}


RARITY_EMOJIS = {
    1: "⚪",
    2: "🟢",
    3: "🔵",
    4: "🟣",
    5: "🟡"
}


def ensure_schema():
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS player_weapons (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    rarity BIGINT NOT NULL,
                    attack BIGINT NOT NULL DEFAULT 0,
                    defense BIGINT NOT NULL DEFAULT 0,
                    equipped BOOLEAN NOT NULL DEFAULT FALSE,
                    obtained_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)


def get_weapons(user_id, username):
    database.ensure_player(user_id, username)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, rarity, attack, defense, equipped
                FROM player_weapons
                WHERE user_id = %s
                ORDER BY rarity DESC, attack DESC, defense DESC
            """, (user_id,))

            return cur.fetchall()


def equip_weapon(user_id, username, weapon_id):
    database.ensure_player(user_id, username)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name
                FROM player_weapons
                WHERE id = %s AND user_id = %s
                FOR UPDATE
            """, (weapon_id, user_id))

            weapon = cur.fetchone()

            if not weapon:
                raise ValueError("Không tìm thấy vũ khí này trong kho của bạn.")

            cur.execute("""
                UPDATE player_weapons
                SET equipped = FALSE
                WHERE user_id = %s
            """, (user_id,))

            cur.execute("""
                UPDATE player_weapons
                SET equipped = TRUE
                WHERE id = %s AND user_id = %s
            """, (weapon_id, user_id))

            return weapon["name"]


def unequip_weapon(user_id, username):
    database.ensure_player(user_id, username)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE player_weapons
                SET equipped = FALSE
                WHERE user_id = %s AND equipped = TRUE
                RETURNING name
            """, (user_id,))

            weapon = cur.fetchone()

            if not weapon:
                raise ValueError("Bạn hiện không trang bị vũ khí nào.")

            return weapon["name"]


class Weapons(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    weapons_group = app_commands.Group(
        name="weapons",
        description="Quản lý vũ khí"
    )

    @weapons_group.command(
        name="list",
        description="Xem kho vũ khí"
    )
    async def list_weapons(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await asyncio.to_thread(ensure_schema)

            weapons = await asyncio.to_thread(
                get_weapons,
                interaction.user.id,
                interaction.user.name
            )

            embed = discord.Embed(
                title=f"⚔️ Kho vũ khí của {interaction.user.display_name}",
                color=discord.Color.blurple()
            )

            if not weapons:
                embed.description = "Bạn chưa sở hữu vũ khí nào."
            else:
                for weapon in weapons[:25]:
                    rarity = weapon["rarity"]
                    emoji = RARITY_EMOJIS.get(rarity, "⚪")
                    rarity_name = RARITY_NAMES.get(rarity, "Unknown")

                    status = "✅ Đang trang bị" if weapon["equipped"] else "Chưa trang bị"

                    embed.add_field(
                        name=(
                            f"{emoji} {weapon['name']} "
                            f"[ID: {weapon['id']}]"
                        ),
                        value=(
                            f"Độ hiếm: **{rarity_name}**\n"
                            f"ATK: **{weapon['attack']}** | "
                            f"DEF: **{weapon['defense']}**\n"
                            f"{status}"
                        ),
                        inline=False
                    )

                if len(weapons) > 25:
                    embed.set_footer(
                        text=f"Đang hiển thị 25/{len(weapons)} vũ khí."
                    )

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] weapons list: {repr(e)}", flush=True)

            await interaction.followup.send(
                "Không thể tải kho vũ khí.",
                ephemeral=True
            )

    @weapons_group.command(
        name="equip",
        description="Trang bị một vũ khí"
    )
    @app_commands.describe(
        weapon_id="ID của vũ khí trong kho"
    )
    async def equip(
        self,
        interaction: discord.Interaction,
        weapon_id: int
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await asyncio.to_thread(ensure_schema)

            weapon_name = await asyncio.to_thread(
                equip_weapon,
                interaction.user.id,
                interaction.user.name,
                weapon_id
            )

            await interaction.followup.send(
                f"⚔️ Bạn đã trang bị **{weapon_name}**.",
                ephemeral=True
            )

        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)

        except Exception as e:
            print(f"[ERROR] weapons equip: {repr(e)}", flush=True)

            await interaction.followup.send(
                "Không thể trang bị vũ khí.",
                ephemeral=True
            )

    @weapons_group.command(
        name="unequip",
        description="Tháo vũ khí đang trang bị"
    )
    async def unequip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await asyncio.to_thread(ensure_schema)

            weapon_name = await asyncio.to_thread(
                unequip_weapon,
                interaction.user.id,
                interaction.user.name
            )

            await interaction.followup.send(
                f"Bạn đã tháo **{weapon_name}**.",
                ephemeral=True
            )

        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)

        except Exception as e:
            print(f"[ERROR] weapons unequip: {repr(e)}", flush=True)

            await interaction.followup.send(
                "Không thể tháo vũ khí.",
                ephemeral=True
            )


async def setup(bot):
    await asyncio.to_thread(ensure_schema)
    await bot.add_cog(Weapons(bot))
