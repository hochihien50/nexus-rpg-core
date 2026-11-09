import asyncio

import discord
from discord import app_commands

import database


ACHIEVEMENTS = {
    "first_kingdom": {
        "name": "👑 Người sáng lập",
        "description": "Thành lập vương quốc đầu tiên.",
        "gold": 200,
        "condition": "kingdom"
    },
    "builder_1": {
        "name": "🏗️ Kiến trúc sư",
        "description": "Nâng cấp tổng cộng 5 cấp công trình.",
        "gold": 300,
        "condition": "buildings",
        "target": 5
    },
    "builder_2": {
        "name": "🏰 Đại kiến trúc sư",
        "description": "Nâng cấp tổng cộng 20 cấp công trình.",
        "gold": 1000,
        "condition": "buildings",
        "target": 20
    },
    "researcher": {
        "name": "🔬 Nhà nghiên cứu",
        "description": "Đạt tổng cộng 5 cấp công nghệ.",
        "gold": 500,
        "condition": "technologies",
        "target": 5
    },
    "population_100": {
        "name": "🏘️ Thành phố đông đúc",
        "description": "Đạt 100 dân.",
        "gold": 500,
        "condition": "population",
        "target": 100
    },
    "population_500": {
        "name": "🌆 Đô thị lớn",
        "description": "Đạt 500 dân.",
        "gold": 1500,
        "condition": "population",
        "target": 500
    },
    "event_10": {
        "name": "🌪️ Người sống sót",
        "description": "Trải qua 10 sự kiện Kingdom.",
        "gold": 700,
        "condition": "events",
        "target": 10
    },
    "kingdom_level_10": {
        "name": "⭐ Đế chế hùng mạnh",
        "description": "Đạt cấp vương quốc 10.",
        "gold": 2000,
        "condition": "level",
        "target": 10
    }
}


def ensure_schema():
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_achievement_claims (
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    achievement_id TEXT NOT NULL,
                    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, achievement_id)
                )
            """)


def get_progress(user_id, username):
    database.ensure_player(user_id, username)

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT level, population
                FROM kingdoms
                WHERE user_id = %s
            """, (user_id,))
            kingdom = cur.fetchone()

            if not kingdom:
                return None, {}

            cur.execute("""
                SELECT COALESCE(SUM(level), 0) AS total
                FROM kingdom_buildings
                WHERE user_id = %s
            """, (user_id,))
            buildings = int(cur.fetchone()["total"])

            cur.execute("""
                SELECT COALESCE(SUM(level), 0) AS total
                FROM kingdom_technologies
                WHERE user_id = %s
            """, (user_id,))
            technologies = int(cur.fetchone()["total"])

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM kingdom_event_history
                WHERE user_id = %s
            """, (user_id,))
            events = int(cur.fetchone()["total"])

            progress = {
                "kingdom": 1,
                "buildings": buildings,
                "technologies": technologies,
                "population": int(kingdom["population"]),
                "events": events,
                "level": int(kingdom["level"])
            }

            cur.execute("""
                SELECT achievement_id
                FROM kingdom_achievement_claims
                WHERE user_id = %s
            """, (user_id,))
            claimed = {
                row["achievement_id"] for row in cur.fetchall()
            }

            return claimed, progress


def claim_achievement(user_id, username, achievement_id):
    if achievement_id not in ACHIEVEMENTS:
        raise ValueError("Thành tựu không hợp lệ.")

    database.ensure_player(user_id, username)

    achievement = ACHIEVEMENTS[achievement_id]

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT level, population
                FROM kingdoms
                WHERE user_id = %s
                FOR UPDATE
            """, (user_id,))
            kingdom = cur.fetchone()

            if not kingdom:
                raise ValueError("Bạn chưa có vương quốc.")

            cur.execute("""
                SELECT COALESCE(SUM(level), 0) AS total
                FROM kingdom_buildings
                WHERE user_id = %s
            """, (user_id,))
            buildings = int(cur.fetchone()["total"])

            cur.execute("""
                SELECT COALESCE(SUM(level), 0) AS total
                FROM kingdom_technologies
                WHERE user_id = %s
            """, (user_id,))
            technologies = int(cur.fetchone()["total"])

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM kingdom_event_history
                WHERE user_id = %s
            """, (user_id,))
            events = int(cur.fetchone()["total"])

            condition = achievement["condition"]

            values = {
                "kingdom": 1,
                "buildings": buildings,
                "technologies": technologies,
                "population": int(kingdom["population"]),
                "events": events,
                "level": int(kingdom["level"])
            }

            current = values[condition]
            target = achievement.get("target", 1)

            if current < target:
                raise ValueError(
                    f"Chưa hoàn thành. Tiến độ: {current}/{target}."
                )

            cur.execute("""
                INSERT INTO kingdom_achievement_claims (
                    user_id, achievement_id
                )
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING achievement_id
            """, (user_id, achievement_id))

            if not cur.fetchone():
                raise ValueError("Bạn đã nhận phần thưởng này rồi.")

            reward = achievement["gold"]

            cur.execute("""
                UPDATE players
                SET gold = gold + %s
                WHERE user_id = %s
            """, (reward, user_id))

            return reward


class KingdomAchievements:
    def __init__(self, bot):
        self.bot = bot


async def achievements(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        claimed, progress = await asyncio.to_thread(
            get_progress,
            interaction.user.id,
            interaction.user.name
        )

        if claimed is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🏆 Thành tựu Kingdom",
            color=discord.Color.gold()
        )

        for key, achievement in ACHIEVEMENTS.items():
            current = progress[achievement["condition"]]
            target = achievement.get("target", 1)
            completed = current >= target
            received = key in claimed

            if received:
                status = "✅ Đã nhận thưởng"
            elif completed:
                status = "🎁 Đã hoàn thành – có thể nhận"
            else:
                status = f"⏳ Tiến độ: {current}/{target}"

            embed.add_field(
                name=achievement["name"],
                value=(
                    f"{achievement['description']}\n"
                    f"Thưởng: **{achievement['gold']:,} Gold**\n"
                    f"{status}"
                ),
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as error:
        print(f"[ERROR] kingdom achievements: {error!r}", flush=True)
        await interaction.followup.send(
            "Không thể tải thành tựu.",
            ephemeral=True
        )


async def claim(interaction: discord.Interaction, achievement_id: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        reward = await asyncio.to_thread(
            claim_achievement,
            interaction.user.id,
            interaction.user.name,
            achievement_id
        )

        await interaction.followup.send(
            f"🏆 Bạn đã nhận **{reward:,} Gold** từ thành tựu!",
            ephemeral=True
        )

    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)

    except Exception as error:
        print(f"[ERROR] achievement claim: {error!r}", flush=True)
        await interaction.followup.send(
            "Không thể nhận phần thưởng.",
            ephemeral=True
        )


async def setup(bot):
    await asyncio.to_thread(ensure_schema)

    group = bot.tree.get_command("kingdom")

    if group is None:
        raise RuntimeError(
            "Hãy load commands.kingdom trước kingdom_achievements."
        )

    if group.get_command("achievements") is None:
        group.add_command(
            app_commands.Command(
                name="achievements",
                description="Xem thành tựu Kingdom",
                callback=achievements
            )
        )

    if group.get_command("claim_achievement") is None:
        group.add_command(
            app_commands.Command(
                name="claim_achievement",
                description="Nhận thưởng thành tựu",
                callback=claim,
                parameters=[
                    app_commands.Parameter(
                        name="achievement_id",
                        description="Mã thành tựu",
                        required=True,
                        annotation=str
                    )
                ]
            )
        )

    print("Loaded: kingdom achievements", flush=True)
