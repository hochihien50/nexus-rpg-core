import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import database


ITEMS = {
    "small_potion": {
        "name": "Bình máu nhỏ",
        "description": "Hồi 20 HP",
        "type": "potion",
        "value": 20
    },
    "medium_potion": {
        "name": "Bình máu vừa",
        "description": "Hồi 50 HP",
        "type": "potion",
        "value": 50
    },
    "large_potion": {
        "name": "Bình máu lớn",
        "description": "Hồi 100 HP",
        "type": "potion",
        "value": 100
    },
    "epic_potion": {
        "name": "Bình máu cao cấp",
        "description": "Hồi 200 HP",
        "type": "potion",
        "value": 200
    },
    "legendary_potion": {
        "name": "Bình máu huyền thoại",
        "description": "Hồi 500 HP",
        "type": "potion",
        "value": 500
    },
    "wood": {
        "name": "Gỗ",
        "description": "Nguyên liệu xây dựng",
        "type": "material"
    },
    "stone": {
        "name": "Đá",
        "description": "Nguyên liệu xây dựng",
        "type": "material"
    },
    "iron": {
        "name": "Sắt",
        "description": "Nguyên liệu chế tạo",
        "type": "material"
    },
    "food": {
        "name": "Thức ăn",
        "description": "Tài nguyên thực phẩm",
        "type": "material"
    },
    "crystal": {
        "name": "Tinh thể",
        "description": "Nguyên liệu ma thuật",
        "type": "material"
    },
    "rare_material": {
        "name": "Nguyên liệu hiếm",
        "description": "Nguyên liệu quý hiếm",
        "type": "material"
    },
    "magic_crystal": {
        "name": "Tinh thể ma thuật",
        "description": "Nguyên liệu ma thuật cao cấp",
        "type": "material"
    },
    "golden_material": {
        "name": "Nguyên liệu quý",
        "description": "Nguyên liệu cấp Epic",
        "type": "material"
    },
    "ancient_crystal": {
        "name": "Tinh thể cổ đại",
        "description": "Nguyên liệu cổ đại",
        "type": "material"
    },
    "mythic_material": {
        "name": "Nguyên liệu thần thoại",
        "description": "Nguyên liệu cực hiếm",
        "type": "material"
    },
    "ticket_standard": {
        "name": "Vé gacha thường",
        "description": "Dùng cho gacha thường",
        "type": "ticket"
    },
    "ticket_premium": {
        "name": "Vé gacha cao cấp",
        "description": "Dùng cho gacha cao cấp",
        "type": "ticket"
    },
    "ticket_weapon": {
        "name": "Vé gacha vũ khí",
        "description": "Dùng cho gacha vũ khí",
        "type": "ticket"
    }
}


def ensure_schema():
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS player_inventory (
                    user_id BIGINT NOT NULL,
                    item_id TEXT NOT NULL,
                    quantity BIGINT NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, item_id)
                )
            """)


def get_inventory(user_id, username):
    database.ensure_player(user_id, username)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT item_id, quantity
                FROM player_inventory
                WHERE user_id = %s AND quantity > 0
                ORDER BY item_id
            """, (user_id,))

            return cur.fetchall()


def use_item(user_id, username, item_id):
    if item_id not in ITEMS:
        raise ValueError("Vật phẩm không tồn tại.")

    item = ITEMS[item_id]

    if item["type"] != "potion":
        raise ValueError("Vật phẩm này chưa thể sử dụng.")

    database.ensure_player(user_id, username)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT hp
                FROM players
                WHERE user_id = %s
                FOR UPDATE
            """, (user_id,))

            player = cur.fetchone()

            if not player:
                raise ValueError("Không tìm thấy nhân vật.")

            cur.execute("""
                SELECT quantity
                FROM player_inventory
                WHERE user_id = %s AND item_id = %s
                FOR UPDATE
            """, (user_id, item_id))

            inventory_item = cur.fetchone()

            if not inventory_item or inventory_item["quantity"] <= 0:
                raise ValueError("Bạn không có vật phẩm này.")

            old_hp = player["hp"]
            heal = item["value"]
            new_hp = min(100, old_hp + heal)

            if new_hp == old_hp:
                raise ValueError("HP của bạn đã đầy.")

            cur.execute("""
                UPDATE player_inventory
                SET quantity = quantity - 1
                WHERE user_id = %s AND item_id = %s
            """, (user_id, item_id))

            cur.execute("""
                UPDATE players
                SET hp = %s
                WHERE user_id = %s
            """, (new_hp, user_id))

            return old_hp, new_hp


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    inventory_group = app_commands.Group(
        name="inventory",
        description="Quản lý kho đồ"
    )

    @inventory_group.command(
        name="view",
        description="Xem kho đồ của bạn"
    )
    async def view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await asyncio.to_thread(ensure_schema)

            items = await asyncio.to_thread(
                get_inventory,
                interaction.user.id,
                interaction.user.name
            )

            embed = discord.Embed(
                title=f"🎒 Kho đồ của {interaction.user.display_name}",
                color=discord.Color.blurple()
            )

            if not items:
                embed.description = "Kho đồ của bạn đang trống."
            else:
                for row in items:
                    item_id = row["item_id"]
                    quantity = row["quantity"]

                    info = ITEMS.get(item_id)

                    if info:
                        name = info["name"]
                        description = info["description"]
                    else:
                        name = item_id
                        description = "Vật phẩm chưa được phân loại."

                    embed.add_field(
                        name=f"{name} × {quantity:,}",
                        value=description,
                        inline=False
                    )

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            print(f"[ERROR] inventory view: {repr(e)}", flush=True)

            await interaction.followup.send(
                "Không thể tải kho đồ.",
                ephemeral=True
            )

    @inventory_group.command(
        name="use",
        description="Sử dụng vật phẩm"
    )
    @app_commands.describe(item="Mã vật phẩm cần sử dụng")
    @app_commands.choices(
        item=[
            app_commands.Choice(name="Bình máu nhỏ", value="small_potion"),
            app_commands.Choice(name="Bình máu vừa", value="medium_potion"),
            app_commands.Choice(name="Bình máu lớn", value="large_potion"),
            app_commands.Choice(name="Bình máu cao cấp", value="epic_potion"),
            app_commands.Choice(name="Bình máu huyền thoại", value="legendary_potion")
        ]
    )
    async def use(
        self,
        interaction: discord.Interaction,
        item: app_commands.Choice[str]
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            old_hp, new_hp = await asyncio.to_thread(
                use_item,
                interaction.user.id,
                interaction.user.name,
                item.value
            )

            await interaction.followup.send(
                f"Bạn đã sử dụng **{ITEMS[item.value]['name']}**.\n"
                f"HP: **{old_hp} → {new_hp}**",
                ephemeral=True
            )

        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)

        except Exception as e:
            print(f"[ERROR] inventory use: {repr(e)}", flush=True)

            await interaction.followup.send(
                "Không thể sử dụng vật phẩm.",
                ephemeral=True
            )


async def setup(bot):
    await asyncio.to_thread(ensure_schema)
    await bot.add_cog(Inventory(bot))
