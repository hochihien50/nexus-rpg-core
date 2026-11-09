import asyncio
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import database


BANNERS = {
    "standard": {
        "name": "Gacha thường",
        "gold_cost": 100,
        "gem_cost": 0,
        "ticket": "ticket_standard",
        "pity_limit": 80,
        "rates": [
            (1, 60.0),
            (2, 28.0),
            (3, 10.0),
            (4, 1.8),
            (5, 0.2)
        ]
    },
    "premium": {
        "name": "Gacha cao cấp",
        "gold_cost": 0,
        "gem_cost": 10,
        "ticket": "ticket_premium",
        "pity_limit": 70,
        "rates": [
            (1, 0.0),
            (2, 20.0),
            (3, 50.0),
            (4, 25.0),
            (5, 5.0)
        ]
    },
    "weapon": {
        "name": "Gacha vũ khí",
        "gold_cost": 150,
        "gem_cost": 0,
        "ticket": "ticket_weapon",
        "pity_limit": 80,
        "rates": [
            (1, 45.0),
            (2, 30.0),
            (3, 18.0),
            (4, 6.0),
            (5, 1.0)
        ]
    }
}


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


ITEM_POOL = {
    1: [
        ("small_potion", "Bình máu nhỏ"),
        ("wood", "Gỗ"),
        ("stone", "Đá")
    ],
    2: [
        ("medium_potion", "Bình máu vừa"),
        ("iron", "Sắt"),
        ("food", "Thức ăn")
    ],
    3: [
        ("large_potion", "Bình máu lớn"),
        ("crystal", "Tinh thể"),
        ("rare_material", "Nguyên liệu hiếm")
    ],
    4: [
        ("epic_potion", "Bình máu cao cấp"),
        ("magic_crystal", "Tinh thể ma thuật"),
        ("golden_material", "Nguyên liệu quý")
    ],
    5: [
        ("legendary_potion", "Bình máu huyền thoại"),
        ("ancient_crystal", "Tinh thể cổ đại"),
        ("mythic_material", "Nguyên liệu thần thoại")
    ]
}


WEAPON_POOL = {
    1: [
        ("Kiếm gỗ", 5, 1),
        ("Dao cũ", 4, 0)
    ],
    2: [
        ("Kiếm sắt", 10, 2),
        ("Khiên sắt", 3, 8)
    ],
    3: [
        ("Kiếm hiệp sĩ", 18, 5),
        ("Cung săn", 15, 3)
    ],
    4: [
        ("Kiếm ma thuật", 30, 8),
        ("Thương sấm sét", 35, 4)
    ],
    5: [
        ("Thánh kiếm", 55, 15),
        ("Hắc kiếm cổ đại", 65, 8)
    ]
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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS gacha_pity (
                    user_id BIGINT NOT NULL,
                    banner TEXT NOT NULL,
                    pulls_since_rare BIGINT NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, banner)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS gacha_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    banner TEXT NOT NULL,
                    reward_type TEXT NOT NULL,
                    reward_name TEXT NOT NULL,
                    rarity BIGINT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)


def roll_rarity(banner, pity):
    config = BANNERS[banner]

    if pity + 1 >= config["pity_limit"]:
        return 5

    rates = config["rates"]
    values = [x[0] for x in rates]
    weights = [x[1] for x in rates]

    return random.choices(values, weights=weights, k=1)[0]


def generate_reward(banner, rarity):
    if banner == "weapon":
        name, attack, defense = random.choice(WEAPON_POOL[rarity])

        return {
            "type": "weapon",
            "name": name,
            "rarity": rarity,
            "attack": attack,
            "defense": defense
        }

    item_id, name = random.choice(ITEM_POOL[rarity])

    return {
        "type": "item",
        "item_id": item_id,
        "name": name,
        "rarity": rarity,
        "quantity": 1
    }


def perform_gacha(user_id, username, banner, amount, payment):
    config = BANNERS[banner]

    database.ensure_player(user_id, username)

    rewards = []

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gold, gems FROM players WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )

            player = cur.fetchone()

            if not player:
                raise RuntimeError("Không tìm thấy người chơi.")

            if payment == "ticket":
                ticket_id = config["ticket"]

                cur.execute("""
                    SELECT quantity
                    FROM player_inventory
                    WHERE user_id = %s AND item_id = %s
                    FOR UPDATE
                """, (user_id, ticket_id))

                row = cur.fetchone()
                ticket_count = row["quantity"] if row else 0

                if ticket_count < amount:
                    raise ValueError(
                        f"Bạn chỉ có {ticket_count} vé, cần {amount} vé."
                    )

                cur.execute("""
                    UPDATE player_inventory
                    SET quantity = quantity - %s
                    WHERE user_id = %s AND item_id = %s
                """, (amount, user_id, ticket_id))

            elif payment == "gold":
                cost = config["gold_cost"] * amount

                if cost <= 0:
                    raise ValueError("Banner này không sử dụng Gold.")

                if player["gold"] < cost:
                    raise ValueError(
                        f"Bạn không đủ Gold. Cần {cost:,} Gold."
                    )

                cur.execute("""
                    UPDATE players
                    SET gold = gold - %s
                    WHERE user_id = %s
                """, (cost, user_id))

            elif payment == "gems":
                cost = config["gem_cost"] * amount

                if cost <= 0:
                    raise ValueError("Banner này không sử dụng Gems.")

                if player["gems"] < cost:
                    raise ValueError(
                        f"Bạn không đủ Gems. Cần {cost:,} Gems."
                    )

                cur.execute("""
                    UPDATE players
                    SET gems = gems - %s
                    WHERE user_id = %s
                """, (cost, user_id))

            else:
                raise ValueError("Phương thức thanh toán không hợp lệ.")

            cur.execute("""
                INSERT INTO gacha_pity (user_id, banner, pulls_since_rare)
                VALUES (%s, %s, 0)
                ON CONFLICT (user_id, banner) DO NOTHING
            """, (user_id, banner))

            cur.execute("""
                SELECT pulls_since_rare
                FROM gacha_pity
                WHERE user_id = %s AND banner = %s
                FOR UPDATE
            """, (user_id, banner))

            pity_row = cur.fetchone()
            pity = pity_row["pulls_since_rare"]

            for _ in range(amount):
                rarity = roll_rarity(banner, pity)
                reward = generate_reward(banner, rarity)

                if rarity >= 4:
                    pity = 0
                else:
                    pity += 1

                if reward["type"] == "item":
                    cur.execute("""
                        INSERT INTO player_inventory (
                            user_id, item_id, quantity
                        )
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, item_id)
                        DO UPDATE SET quantity =
                            player_inventory.quantity + EXCLUDED.quantity
                    """, (
                        user_id,
                        reward["item_id"],
                        reward["quantity"]
                    ))

                else:
                    cur.execute("""
                        INSERT INTO player_weapons (
                            user_id, name, rarity, attack, defense
                        )
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        reward["name"],
                        reward["rarity"],
                        reward["attack"],
                        reward["defense"]
                    ))

                cur.execute("""
                    INSERT INTO gacha_history (
                        user_id, banner, reward_type, reward_name, rarity
                    )
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    user_id,
                    banner,
                    reward["type"],
                    reward["name"],
                    rarity
                ))

                rewards.append(reward)

            cur.execute("""
                UPDATE gacha_pity
                SET pulls_since_rare = %s
                WHERE user_id = %s AND banner = %s
            """, (pity, user_id, banner))

    return rewards, pity


class Gacha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="gacha",
        description="Quay gacha để nhận vật phẩm hoặc vũ khí"
    )
    @app_commands.describe(
        banner="Loại gacha",
        amount="Số lượt quay",
        payment="Phương thức thanh toán"
    )
    @app_commands.choices(
        banner=[
            app_commands.Choice(name="Gacha thường", value="standard"),
            app_commands.Choice(name="Gacha cao cấp", value="premium"),
            app_commands.Choice(name="Gacha vũ khí", value="weapon")
        ],
        amount=[
            app_commands.Choice(name="1 lượt", value=1),
            app_commands.Choice(name="10 lượt", value=10)
        ],
        payment=[
            app_commands.Choice(name="Gold", value="gold"),
            app_commands.Choice(name="Gems", value="gems"),
            app_commands.Choice(name="Ticket", value="ticket")
        ]
    )
    async def gacha(
        self,
        interaction: discord.Interaction,
        banner: app_commands.Choice[str],
        amount: app_commands.Choice[int],
        payment: app_commands.Choice[str]
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await asyncio.to_thread(ensure_schema)

            rewards, pity = await asyncio.to_thread(
                perform_gacha,
                interaction.user.id,
                interaction.user.name,
                banner.value,
                amount.value,
                payment.value
            )

            embed = discord.Embed(
                title=f"🎲 {BANNERS[banner.value]['name']}",
                description=f"Bạn đã quay **{amount.value} lượt**.",
                color=discord.Color.blurple()
            )

            for reward in rewards:
                rarity = reward["rarity"]
                prefix = RARITY_EMOJIS[rarity]
                rarity_name = RARITY_NAMES[rarity]

                if reward["type"] == "weapon":
                    detail = (
                        f"ATK: **{reward['attack']}** | "
                        f"DEF: **{reward['defense']}**"
                    )
                else:
                    detail = f"Vật phẩm: `{reward['item_id']}`"

                embed.add_field(
                    name=f"{prefix} {reward['name']} – {rarity_name}",
                    value=detail,
                    inline=False
                )

            embed.set_footer(
                text=f"Pity hiện tại: {pity}/{BANNERS[banner.value]['pity_limit']}"
            )

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)

        except Exception as e:
            print(f"[ERROR] gacha: {repr(e)}", flush=True)

            await interaction.followup.send(
                "Có lỗi khi quay gacha. Vui lòng thử lại sau.",
                ephemeral=True
            )


async def setup(bot):
    await asyncio.to_thread(ensure_schema)
    await bot.add_cog(Gacha(bot))
