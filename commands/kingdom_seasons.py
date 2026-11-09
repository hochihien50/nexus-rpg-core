import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands

import database


def current_season():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def ensure_schema():
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_season_scores (
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    season_id TEXT NOT NULL,
                    points BIGINT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, season_id)
                )
            """)


def calculate_score(user_id):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT level, xp, population
                FROM kingdoms
                WHERE user_id = %s
            """, (user_id,))

            kingdom = cur.fetchone()

            if not kingdom:
                return None

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
                SELECT COALESCE(SUM(workers), 0) AS total
                FROM kingdom_workers
                WHERE user_id = %s
            """, (user_id,))
            workers = int(cur.fetchone()["total"])

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM kingdom_event_history
                WHERE user_id = %s
            """, (user_id,))
            events = int(cur.fetchone()["total"])

            points = (
                int(kingdom["xp"])
                + int(kingdom["level"]) * 100
                + buildings * 100
                + technologies * 150
                + int(kingdom["population"]) * 2
                + workers
                + int(events) * 10
            )

            return max(0, points)


def update_season_score(user_id):
    season_id = current_season()
    points = calculate_score(user_id)

    if points is None:
        return None

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kingdom_season_scores (
                    user_id, season_id, points
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, season_id)
                DO UPDATE SET
                    points = EXCLUDED.points,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, season_id, points))

    return season_id, points


async def season(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        result = await asyncio.to_thread(
            update_season_score,
            interaction.user.id
        )

        if result is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        season_id, points = result

        embed = discord.Embed(
            title=f"🏆 Kingdom Season {season_id}",
            description=(
                f"Vương quốc: **{interaction.user.display_name}**\n"
                f"Điểm mùa hiện tại: **{points:,}**"
            ),
            color=discord.Color.gold()
        )

        embed.add_field(
            name="Cách tính điểm",
            value=(
                "• XP Kingdom: 1 điểm/XP\n"
                "• Cấp vương quốc: 100 điểm/cấp\n"
                "• Cấp công trình: 100 điểm/cấp\n"
                "• Cấp công nghệ: 150 điểm/cấp\n"
                "• Dân số: 2 điểm/người\n"
                "• Công nhân: 1 điểm/người\n"
                "• Sự kiện đã trải qua: 10 điểm/sự kiện"
            ),
            inline=False
        )

        embed.set_footer(
            text="Mùa giải chuyển sang tháng mới theo UTC."
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    except Exception as error:
        print(f"[ERROR] kingdom season: {error!r}", flush=True)
        await interaction.followup.send(
            "Không thể tải thông tin mùa giải.",
            ephemeral=True
        )


async def setup(bot):
    await asyncio.to_thread(ensure_schema)

    group = bot.tree.get_command("kingdom")

    if group is None:
        raise RuntimeError(
            "Hãy load commands.kingdom trước kingdom_seasons."
        )

    if group.get_command("season") is None:
        group.add_command(
            app_commands.Command(
                name="season",
                description="Xem mùa giải Kingdom hiện tại",
                callback=season
            )
        )

    print("Loaded: kingdom seasons", flush=True)
