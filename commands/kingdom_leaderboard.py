import asyncio

import discord
from discord import app_commands

import database


def get_leaderboard():
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    k.user_id,
                    k.name,
                    p.username,
                    k.level,
                    k.xp,
                    k.population,

                    COALESCE((
                        SELECT SUM(b.level)
                        FROM kingdom_buildings b
                        WHERE b.user_id = k.user_id
                    ), 0) AS building_levels,

                    COALESCE((
                        SELECT SUM(t.level)
                        FROM kingdom_technologies t
                        WHERE t.user_id = k.user_id
                    ), 0) AS technology_levels,

                    COALESCE((
                        SELECT SUM(w.workers)
                        FROM kingdom_workers w
                        WHERE w.user_id = k.user_id
                    ), 0) AS workers,

                    COALESCE((
                        SELECT COUNT(*)
                        FROM kingdom_event_history e
                        WHERE e.user_id = k.user_id
                    ), 0) AS events

                FROM kingdoms k
                JOIN players p ON p.user_id = k.user_id
                ORDER BY
                    (
                        k.xp
                        + k.level * 100
                        + COALESCE((
                            SELECT SUM(b.level) * 100
                            FROM kingdom_buildings b
                            WHERE b.user_id = k.user_id
                        ), 0)
                        + COALESCE((
                            SELECT SUM(t.level) * 150
                            FROM kingdom_technologies t
                            WHERE t.user_id = k.user_id
                        ), 0)
                        + k.population * 2
                        + COALESCE((
                            SELECT SUM(w.workers)
                            FROM kingdom_workers w
                            WHERE w.user_id = k.user_id
                        ), 0)
                        + COALESCE((
                            SELECT COUNT(*) * 10
                            FROM kingdom_event_history e
                            WHERE e.user_id = k.user_id
                        ), 0)
                    ) DESC,
                    k.level DESC,
                    k.xp DESC

                LIMIT 10
            """)

            rows = cur.fetchall()

            result = []

            for row in rows:
                points = (
                    int(row["xp"])
                    + int(row["level"]) * 100
                    + int(row["building_levels"]) * 100
                    + int(row["technology_levels"]) * 150
                    + int(row["population"]) * 2
                    + int(row["workers"])
                    + int(row["events"]) * 10
                )

                result.append({
                    "user_id": row["user_id"],
                    "name": row["name"],
                    "username": row["username"],
                    "level": row["level"],
                    "population": row["population"],
                    "points": points
                })

            return result


async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        rows = await asyncio.to_thread(get_leaderboard)

        embed = discord.Embed(
            title="🏆 Kingdom Leaderboard",
            description="Top 10 vương quốc mạnh nhất.",
            color=discord.Color.gold()
        )

        if not rows:
            embed.description = "Chưa có vương quốc nào được thành lập."
        else:
            medals = ["🥇", "🥈", "🥉"]

            lines = []

            for index, row in enumerate(rows):
                rank = (
                    medals[index]
                    if index < 3
                    else f"`#{index + 1}`"
                )

                lines.append(
                    f"{rank} **{row['name']}**\n"
                    f"👤 {row['username']} · "
                    f"⭐ Lv.{row['level']} · "
                    f"👥 {row['population']:,} dân\n"
                    f"🏆 **{row['points']:,} điểm**"
                )

            embed.description = "\n\n".join(lines)

        embed.set_footer(
            text="Điểm được tính từ XP, công trình, công nghệ, dân số, công nhân và sự kiện."
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    except Exception as error:
        print(f"[ERROR] kingdom leaderboard: {error!r}", flush=True)

        await interaction.followup.send(
            "Không thể tải bảng xếp hạng.",
            ephemeral=True
        )


async def setup(bot):
    group = bot.tree.get_command("kingdom")

    if group is None:
        raise RuntimeError(
            "Hãy load commands.kingdom trước kingdom_leaderboard."
        )

    if group.get_command("leaderboard") is None:
        group.add_command(
            app_commands.Command(
                name="leaderboard",
                description="Xem bảng xếp hạng Kingdom",
                callback=leaderboard
            )
        )

    print("Loaded: kingdom leaderboard", flush=True)
