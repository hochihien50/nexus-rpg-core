import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import database


BUILDINGS = {
    "farm": ("🌾 Nông trại", 150, 30, 15),
    "lumber": ("🪵 Xưởng gỗ", 180, 25, 10),
    "mine": ("⛏️ Mỏ khoáng", 250, 35, 25),
    "house": ("🏠 Khu dân cư", 200, 40, 20),
    "market": ("🏪 Chợ", 350, 50, 35),
    "castle": ("🏰 Lâu đài", 800, 80, 100),
}

EVENTS = [
    ("🌧️ Mưa thuận gió hòa", "Lương thực +20", "food", 20),
    ("💎 Mạch khoáng mới", "Sắt +12", "iron", 12),
    ("🧳 Đoàn thương nhân", "Kho bạc cá nhân +120 Gold", "gold", 120),
    ("🎉 Lễ hội mùa màng", "Hạnh phúc +8", "happiness", 8),
    ("🌲 Rừng xanh trù phú", "Gỗ +18", "wood", 18),
]


def now():
    return datetime.now(timezone.utc)


def ensure_schema():
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdoms (
                    user_id BIGINT PRIMARY KEY
                        REFERENCES players(user_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 1,
                    xp BIGINT NOT NULL DEFAULT 0,
                    food BIGINT NOT NULL DEFAULT 100,
                    wood BIGINT NOT NULL DEFAULT 100,
                    stone BIGINT NOT NULL DEFAULT 60,
                    iron BIGINT NOT NULL DEFAULT 20,
                    population INTEGER NOT NULL DEFAULT 25,
                    happiness INTEGER NOT NULL DEFAULT 80,
                    stability INTEGER NOT NULL DEFAULT 90,
                    last_collect TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    event_name TEXT,
                    event_until TIMESTAMPTZ
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_buildings (
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    building_key TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, building_key)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_event_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    event_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)


def create_kingdom(user_id, username, name):
    name = name.strip()[:32]
    if not name:
        return False

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO players (user_id, username)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, username)
            )
            cur.execute(
                """
                INSERT INTO kingdoms (user_id, name)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING user_id
                """,
                (user_id, name)
            )
            if cur.fetchone() is None:
                return False

            cur.executemany(
                """
                INSERT INTO kingdom_buildings (user_id, building_key)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                [(user_id, key) for key in BUILDINGS]
            )
            return True


def get_kingdom(user_id):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kingdoms WHERE user_id = %s",
                (user_id,)
            )
            kingdom = cur.fetchone()

            cur.execute(
                """
                SELECT building_key, level
                FROM kingdom_buildings
                WHERE user_id = %s
                """,
                (user_id,)
            )
            buildings = {
                row["building_key"]: row["level"]
                for row in cur.fetchall()
            }
            return kingdom, buildings


def upgrade_building(user_id, key):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gold FROM players WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            player = cur.fetchone()

            cur.execute(
                "SELECT * FROM kingdoms WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            kingdom = cur.fetchone()

            if not player or not kingdom:
                return "missing", None

            cur.execute(
                """
                SELECT level
                FROM kingdom_buildings
                WHERE user_id = %s AND building_key = %s
                FOR UPDATE
                """,
                (user_id, key)
            )
            row = cur.fetchone()
            level = row["level"] if row else 0

            if level >= 10:
                return "max", None

            name, base_gold, base_wood, base_stone = BUILDINGS[key]
            next_level = level + 1
            gold = base_gold * next_level
            wood = base_wood * next_level
            stone = base_stone * next_level

            if (
                player["gold"] < gold
                or kingdom["wood"] < wood
                or kingdom["stone"] < stone
            ):
                return "funds", (gold, wood, stone)

            cur.execute(
                "UPDATE players SET gold = gold - %s WHERE user_id = %s",
                (gold, user_id)
            )
            cur.execute(
                """
                UPDATE kingdoms
                SET wood = wood - %s, stone = stone - %s, xp = xp + %s
                WHERE user_id = %s
                """,
                (wood, stone, next_level * 25, user_id)
            )
            cur.execute(
                """
                UPDATE kingdom_buildings
                SET level = %s
                WHERE user_id = %s AND building_key = %s
                """,
                (next_level, user_id, key)
            )
            cur.execute(
                """
                UPDATE kingdoms
                SET level = GREATEST(level, 1 + (xp / 500)::int)
                WHERE user_id = %s
                """,
                (user_id,)
            )
            return "ok", (name, next_level, gold, wood, stone)


def collect(user_id):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kingdoms WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            kingdom = cur.fetchone()

            if not kingdom:
                return None

            current = now()
            elapsed = current - kingdom["last_collect"]
            minutes = min(
                1440,
                max(0, int(elapsed.total_seconds() // 60))
            )

            if minutes < 1:
                return {"minutes": 0}

            cur.execute(
                """
                SELECT building_key, level
                FROM kingdom_buildings
                WHERE user_id = %s
                """,
                (user_id,)
            )
            levels = {
                row["building_key"]: row["level"]
                for row in cur.fetchall()
            }

            gains = {
                "food": minutes // 10 * levels.get("farm", 0),
                "wood": minutes // 15 * levels.get("lumber", 0),
                "stone": minutes // 20 * levels.get("mine", 0),
                "iron": minutes // 30 * levels.get("mine", 0),
            }
            gains = {
                key: value for key, value in gains.items()
                if value > 0
            }

            event_text = None
            event_active = (
                kingdom["event_until"]
                and kingdom["event_until"] > current
            )

            if event_active:
                event_text = "Đang diễn ra: " + kingdom["event_name"]
            elif random.random() < 0.28:
                event_name, description, resource, amount = random.choice(EVENTS)

                if resource == "gold":
                    cur.execute(
                        "UPDATE players SET gold = gold + %s WHERE user_id = %s",
                        (amount, user_id)
                    )
                elif resource == "happiness":
                    cur.execute(
                        """
                        UPDATE kingdoms
                        SET happiness = LEAST(100, happiness + %s)
                        WHERE user_id = %s
                        """,
                        (amount, user_id)
                    )
                else:
                    gains[resource] = gains.get(resource, 0) + amount

                event_text = event_name + ": " + description
                cur.execute(
                    """
                    INSERT INTO kingdom_event_history
                        (user_id, event_name, description)
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, event_name, description)
                )
                cur.execute(
                    """
                    UPDATE kingdoms
                    SET event_name = %s, event_until = %s
                    WHERE user_id = %s
                    """,
                    (event_name, current + timedelta(hours=3), user_id)
                )

            for resource, amount in gains.items():
                cur.execute(
                    f"""
                    UPDATE kingdoms
                    SET {resource} = {resource} + %s
                    WHERE user_id = %s
                    """,
                    (amount, user_id)
                )

            if kingdom["food"] < 25 and kingdom["happiness"] > 10:
                cur.execute(
                    """
                    UPDATE kingdoms
                    SET happiness = GREATEST(0, happiness - 5)
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                warning = "⚠️ Khan hiếm lương thực: hạnh phúc giảm 5."
                event_text = (event_text + "\n" if event_text else "") + warning

            cur.execute(
                """
                UPDATE kingdoms
                SET last_collect = %s,
                    event_name = CASE
                        WHEN event_until <= %s THEN NULL
                        ELSE event_name
                    END,
                    event_until = CASE
                        WHEN event_until <= %s THEN NULL
                        ELSE event_until
                    END
                WHERE user_id = %s
                """,
                (current, current, current, user_id)
            )

            return {
                "minutes": minutes,
                "gains": gains,
                "event": event_text
            }


class Kingdom(
    commands.GroupCog,
    name="kingdom",
    description="Xây dựng và quản lý vương quốc cá nhân"
):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="create",
        description="👑 Thành lập vương quốc cá nhân"
    )
    @app_commands.describe(name="Tên vương quốc, tối đa 32 ký tự")
    async def create(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            created = await asyncio.to_thread(
                create_kingdom,
                interaction.user.id,
                interaction.user.name,
                name
            )
            if created:
                message = (
                    f"👑 Vương quốc **{name.strip()[:32]}** đã được thành lập!\n"
                    "Dùng `/kingdom overview` để xem lãnh thổ."
                )
            else:
                message = "⚠️ Bạn đã có vương quốc hoặc tên không hợp lệ."

            await interaction.followup.send(message, ephemeral=True)
        except Exception as error:
            print(f"[ERROR] kingdom create: {error!r}", flush=True)
            await interaction.followup.send(
                "Không thể tạo vương quốc. Hãy kiểm tra log bot.",
                ephemeral=True
            )

    @app_commands.command(
        name="overview",
        description="🏰 Xem tổng quan vương quốc"
    )
    async def overview(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            kingdom, buildings = await asyncio.to_thread(
                get_kingdom,
                interaction.user.id
            )

            if not kingdom:
                await interaction.followup.send(
                    "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"🏰 {kingdom['name']}",
                description=(
                    f"👑 {interaction.user.mention} · "
                    f"⭐ Cấp {kingdom['level']} · ✨ {kingdom['xp']} XP"
                ),
                color=discord.Color.gold()
            )
            embed.add_field(
                name="📦 Tài nguyên",
                value=(
                    f"🌾 {kingdom['food']:,} Food\n"
                    f"🪵 {kingdom['wood']:,} Wood\n"
                    f"🪨 {kingdom['stone']:,} Stone\n"
                    f"⛓️ {kingdom['iron']:,} Iron"
                )
            )
            embed.add_field(
                name="🏘️ Dân sinh",
                value=(
                    f"👥 {kingdom['population']:,}\n"
                    f"😊 {kingdom['happiness']}/100\n"
                    f"🛡️ {kingdom['stability']}/100"
                )
            )
            embed.add_field(
                name="🏗️ Công trình",
                value="\n".join(
                    f"{BUILDINGS[key][0]}: cấp **{buildings.get(key, 0)}**"
                    for key in BUILDINGS
                ),
                inline=False
            )

            if (
                kingdom["event_name"]
                and kingdom["event_until"]
                and kingdom["event_until"] > now()
            ):
                embed.add_field(
                    name="🌪️ Biến cố",
                    value=kingdom["event_name"],
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as error:
            print(f"[ERROR] kingdom overview: {error!r}", flush=True)
            await interaction.followup.send(
                "Không thể tải vương quốc. Hãy kiểm tra log bot.",
                ephemeral=True
            )

    @app_commands.command(
        name="build",
        description="🔨 Xây hoặc nâng cấp công trình"
    )
    @app_commands.choices(building=[
        app_commands.Choice(name="🌾 Nông trại", value="farm"),
        app_commands.Choice(name="🪵 Xưởng gỗ", value="lumber"),
        app_commands.Choice(name="⛏️ Mỏ khoáng", value="mine"),
        app_commands.Choice(name="🏠 Khu dân cư", value="house"),
        app_commands.Choice(name="🏪 Chợ", value="market"),
        app_commands.Choice(name="🏰 Lâu đài", value="castle"),
    ])
    async def build(
        self,
        interaction: discord.Interaction,
        building: app_commands.Choice[str]
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            status, result = await asyncio.to_thread(
                upgrade_building,
                interaction.user.id,
                building.value
            )

            if status == "missing":
                message = "Bạn chưa có vương quốc. Dùng `/kingdom create`."
            elif status == "max":
                message = "🏆 Công trình đã đạt cấp tối đa 10."
            elif status == "funds":
                gold, wood, stone = result
                message = (
                    f"❌ Cần **{gold:,} Gold**, **{wood:,} Wood** "
                    f"và **{stone:,} Stone**."
                )
            else:
                name, level, gold, wood, stone = result
                message = (
                    f"🔨 {name} đã lên cấp **{level}**!\n"
                    f"💰 -{gold:,} Gold · 🪵 -{wood:,} Wood · "
                    f"🪨 -{stone:,} Stone"
                )

            await interaction.followup.send(message, ephemeral=True)
        except Exception as error:
            print(f"[ERROR] kingdom build: {error!r}", flush=True)
            await interaction.followup.send(
                "Không thể xây dựng. Hãy kiểm tra log bot.",
                ephemeral=True
            )

    @app_commands.command(
        name="collect",
        description="📦 Thu thập sản lượng và xử lý biến cố"
    )
    async def collect_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await asyncio.to_thread(collect, interaction.user.id)

            if result is None:
                message = "Bạn chưa có vương quốc. Dùng `/kingdom create`."
            elif result["minutes"] == 0:
                message = "⏳ Chưa có sản lượng mới. Hãy quay lại sau ít phút."
            else:
                labels = {
                    "food": "🌾 Food",
                    "wood": "🪵 Wood",
                    "stone": "🪨 Stone",
                    "iron": "⛓️ Iron"
                }
                lines = [
                    f"{labels[key]}: **+{value:,}**"
                    for key, value in result["gains"].items()
                ]
                message = (
                    f"📦 Thu hoạch sau {result['minutes']} phút.\n"
                    + ("\n".join(lines) if lines else
                       "Chưa có sản lượng từ công trình.")
                )
                if result["event"]:
                    message += "\n\n🌪️ **Biến động:**\n" + result["event"]

            await interaction.followup.send(message, ephemeral=True)
        except Exception as error:
            print(f"[ERROR] kingdom collect: {error!r}", flush=True)
            await interaction.followup.send(
                "Không thể thu thập. Hãy kiểm tra log bot.",
                ephemeral=True
            )


async def setup(bot):
    await asyncio.to_thread(ensure_schema)
    await bot.add_cog(Kingdom(bot))
