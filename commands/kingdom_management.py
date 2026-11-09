import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

import database


MAX_OFFLINE_HOURS = 24
WAREHOUSE_CAPACITY = 5000
FOOD_PER_PERSON_HOUR = 0.08

JOBS = {
    "farmer": ("🌾 Farmer", {"food": 6.0}, "farm"),
    "miner": ("⛏️ Miner", {"stone": 2.0, "iron": 0.7}, "mine"),
    "lumberjack": ("🪵 Lumberjack", {"wood": 3.0}, "lumber"),
    "blacksmith": ("⚒️ Blacksmith", {"metal_parts": 0.8}, "castle"),
    "merchant": ("💰 Merchant", {"gold": 2.0}, "market"),
    "fisherman": ("🐟 Fisherman", {"fish": 2.0}, "market"),
    "herbalist": ("🌿 Herbalist", {"herbs": 1.0}, "farm"),
    "alchemist": ("⚗️ Alchemist", {"potion_materials": 0.5}, "castle"),
    "engineer": ("🛠️ Engineer", {"advanced_materials": 0.5}, "mine"),
    "scholar": ("📚 Scholar", {"research_points": 1.0}, "castle"),
}

RESOURCE_LABELS = {
    "food": "🌾 Food",
    "wood": "🪵 Wood",
    "stone": "🪨 Stone",
    "iron": "⛓️ Iron",
    "gold": "💰 Gold",
    "fish": "🐟 Fish",
    "herbs": "🌿 Herbs",
    "metal_parts": "⚒️ Metal Parts",
    "potion_materials": "⚗️ Potion Materials",
    "advanced_materials": "🛠️ Advanced Materials",
    "research_points": "📚 Research Points",
}

TECHNOLOGIES = {
    "agriculture": ("Advanced Agriculture", "Tăng sản lượng Farmer"),
    "mining": ("Mining Techniques", "Tăng sản lượng Miner"),
    "forestry": ("Forestry", "Tăng sản lượng Lumberjack"),
    "metallurgy": ("Metallurgy", "Tăng sản lượng Blacksmith"),
    "trade": ("Trade Routes", "Tăng sản lượng Merchant"),
    "architecture": ("Architecture", "Tăng sức chứa nhà ở"),
    "military": ("Military Engineering", "Công nghệ hỗ trợ chiến tranh"),
}

EVENTS = [
    ("Great Harvest", "Farmer tăng 30% sản lượng trong 3 giờ.", "farmer", 1.30, "production"),
    ("Mining Discovery", "Miner tăng 30% sản lượng trong 3 giờ.", "miner", 1.30, "production"),
    ("Worker Strike", "Toàn bộ công nhân giảm 20% sản lượng trong 3 giờ.", "all", 0.80, "production"),
    ("Merchant Caravan", "Merchant tăng 40% sản lượng trong 3 giờ.", "merchant", 1.40, "production"),
    ("Festival", "Happiness tăng 8 điểm.", "happiness", 1.0, "instant"),
    ("Skilled Immigrants", "Vương quốc nhận thêm 2 dân.", "population", 1.0, "instant"),
]


def ensure_schema():
    """Create the management tables and migrate existing kingdoms safely."""
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_population (
                    user_id BIGINT PRIMARY KEY
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    housing_capacity INTEGER NOT NULL DEFAULT 50,
                    happiness INTEGER NOT NULL DEFAULT 80,
                    growth_progress NUMERIC(12, 6) NOT NULL DEFAULT 0,
                    last_tick TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_workers (
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    profession TEXT NOT NULL,
                    workers INTEGER NOT NULL DEFAULT 0 CHECK (workers >= 0),
                    xp BIGINT NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    fatigue NUMERIC(7, 2) NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, profession)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_extra_resources (
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    resource TEXT NOT NULL,
                    amount BIGINT NOT NULL DEFAULT 0 CHECK (amount >= 0),
                    PRIMARY KEY (user_id, resource)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_technologies (
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    technology TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 0 CHECK (level >= 0),
                    PRIMARY KEY (user_id, technology)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_active_events (
                    user_id BIGINT PRIMARY KEY
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    event_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    target TEXT NOT NULL,
                    multiplier NUMERIC(6, 3) NOT NULL DEFAULT 1,
                    event_type TEXT NOT NULL DEFAULT 'production',
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kingdom_production_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL
                        REFERENCES kingdoms(user_id) ON DELETE CASCADE,
                    profession TEXT NOT NULL,
                    hours NUMERIC(8, 3) NOT NULL,
                    produced JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                INSERT INTO kingdom_population (user_id, happiness)
                SELECT user_id, happiness FROM kingdoms
                ON CONFLICT (user_id) DO NOTHING
            """)

            for profession in JOBS:
                cur.execute("""
                    INSERT INTO kingdom_workers (user_id, profession)
                    SELECT user_id, %s FROM kingdoms
                    ON CONFLICT (user_id, profession) DO NOTHING
                """, (profession,))

            for resource in (
                "fish", "herbs", "metal_parts", "potion_materials",
                "advanced_materials", "research_points"
            ):
                cur.execute("""
                    INSERT INTO kingdom_extra_resources (user_id, resource, amount)
                    SELECT user_id, %s, 0 FROM kingdoms
                    ON CONFLICT (user_id, resource) DO NOTHING
                """, (resource,))


def _building_levels(cur, user_id):
    cur.execute(
        "SELECT building_key, level FROM kingdom_buildings WHERE user_id = %s",
        (user_id,)
    )
    return {row["building_key"]: int(row["level"]) for row in cur.fetchall()}


def _add_resource(cur, user_id, resource, amount, capacity):
    amount = max(0, int(amount))
    if amount == 0:
        return 0

    if resource in ("food", "wood", "stone", "iron"):
        cur.execute(
            f"""UPDATE kingdoms
                SET {resource} = LEAST(%s, {resource} + %s)
                WHERE user_id = %s""",
            (capacity, amount, user_id)
        )
    elif resource == "gold":
        cur.execute(
            "UPDATE players SET gold = gold + %s WHERE user_id = %s",
            (amount, user_id)
        )
    else:
        cur.execute("""
            INSERT INTO kingdom_extra_resources (user_id, resource, amount)
            VALUES (%s, %s, LEAST(%s, %s))
            ON CONFLICT (user_id, resource) DO UPDATE
            SET amount = LEAST(
                %s,
                kingdom_extra_resources.amount + EXCLUDED.amount
            )
        """, (user_id, resource, capacity, amount, capacity))


def _new_event(cur, user_id, now):
    name, description, target, multiplier, event_type = random.choice(EVENTS)
    expires = now + timedelta(hours=3)

    if event_type == "instant":
        if target == "happiness":
            cur.execute("""
                UPDATE kingdoms
                SET happiness = LEAST(100, happiness + 8)
                WHERE user_id = %s
            """, (user_id,))
            cur.execute("""
                UPDATE kingdom_population
                SET happiness = LEAST(100, happiness + 8)
                WHERE user_id = %s
            """, (user_id,))
        elif target == "population":
            cur.execute("""
                UPDATE kingdoms
                SET population = LEAST(population + 2, 100000)
                WHERE user_id = %s
            """, (user_id,))
        return {"event_name": name, "description": description, "expires_at": expires}

    cur.execute("""
        INSERT INTO kingdom_active_events
            (user_id, event_name, description, target, multiplier, event_type, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            event_name = EXCLUDED.event_name,
            description = EXCLUDED.description,
            target = EXCLUDED.target,
            multiplier = EXCLUDED.multiplier,
            event_type = EXCLUDED.event_type,
            expires_at = EXCLUDED.expires_at
    """, (user_id, name, description, target, multiplier, event_type, expires))
    return {"event_name": name, "description": description, "expires_at": expires}


def _advance(cur, user_id, kingdom):
    """Accrue up to 24h once, under the caller's kingdom row lock."""
    now = datetime.now(timezone.utc)

    cur.execute(
        "SELECT * FROM kingdom_population WHERE user_id = %s FOR UPDATE",
        (user_id,)
    )
    population = cur.fetchone()

    if population is None:
        cur.execute("""
            INSERT INTO kingdom_population (user_id, happiness)
            VALUES (%s, %s)
            RETURNING *
        """, (user_id, int(kingdom["happiness"])))
        population = cur.fetchone()

    elapsed = max(
        0.0,
        (now - population["last_tick"]).total_seconds() / 3600
    )
    hours = min(float(MAX_OFFLINE_HOURS), elapsed)

    if hours <= 0:
        return {
            "hours": 0.0, "gains": {}, "consumed": 0,
            "happiness": int(population["happiness"]), "event": None
        }

    buildings = _building_levels(cur, user_id)
    warehouse_capacity = WAREHOUSE_CAPACITY + buildings.get("warehouse", 0) * 2500
    housing_capacity = 50 + buildings.get("house", 0) * 20

    cur.execute(
        "SELECT technology, level FROM kingdom_technologies WHERE user_id = %s",
        (user_id,)
    )
    tech = {row["technology"]: int(row["level"]) for row in cur.fetchall()}

    cur.execute(
        "SELECT * FROM kingdom_workers WHERE user_id = %s FOR UPDATE",
        (user_id,)
    )
    worker_rows = cur.fetchall()

    cur.execute("""
        SELECT * FROM kingdom_active_events
        WHERE user_id = %s AND expires_at > %s
        FOR UPDATE
    """, (user_id, now))
    active_event = cur.fetchone()

    happiness = max(0, min(100, int(population["happiness"])))
    happiness_modifier = 0.60 + happiness / 250.0
    gains = {}
    history = []

    for worker in worker_rows:
        profession = worker["profession"]
        count = int(worker["workers"])
        if profession not in JOBS:
            continue

        fatigue = float(worker["fatigue"])
        if count > 0:
            fatigue = min(100.0, fatigue + hours * 1.25)
        else:
            fatigue = max(0.0, fatigue - hours * 3.0)

        if count <= 0:
            cur.execute("""
                UPDATE kingdom_workers SET fatigue = %s
                WHERE user_id = %s AND profession = %s
            """, (fatigue, user_id, profession))
            continue

        _, outputs, building_key = JOBS[profession]
        building_modifier = 1.0 + min(
            0.50, buildings.get(building_key, 0) * 0.05
        )
        specialization_level = int(worker["level"])
        specialization_modifier = 1.0 + min(
            0.35, max(0, specialization_level - 1) * 0.05
        )

        tech_key = {
            "farmer": "agriculture",
            "miner": "mining",
            "lumberjack": "forestry",
            "blacksmith": "metallurgy",
            "merchant": "trade",
        }.get(profession)
        tech_modifier = (
            1.0 + tech.get(tech_key, 0) * 0.10
            if tech_key else 1.0
        )
        fatigue_modifier = max(0.30, 1.0 - fatigue * 0.006)
        event_modifier = 1.0

        if (
            active_event
            and active_event["event_type"] == "production"
            and active_event["target"] in (profession, "all")
        ):
            event_modifier = float(active_event["multiplier"])

        modifier = (
            happiness_modifier * building_modifier
            * specialization_modifier * tech_modifier
            * fatigue_modifier * event_modifier
        )

        produced = {}
        for resource, rate in outputs.items():
            amount = int(count * rate * hours * modifier)
            if amount > 0:
                gains[resource] = gains.get(resource, 0) + amount
                produced[resource] = amount

        xp = int(worker["xp"]) + int(count * hours)
        level = min(20, 1 + xp // 500)

        cur.execute("""
            UPDATE kingdom_workers
            SET xp = %s, level = %s, fatigue = %s
            WHERE user_id = %s AND profession = %s
        """, (xp, level, fatigue, user_id, profession))

        history.append((profession, hours, produced))

    # Add production before food consumption so farmers can feed the population.
    for resource, amount in gains.items():
        _add_resource(cur, user_id, resource, amount, warehouse_capacity)

    population_count = int(kingdom["population"])
    food_consumption = int(round(
        population_count * FOOD_PER_PERSON_HOUR * hours
    ))
    food_before_consumption = int(kingdom["food"]) + gains.get("food", 0)
    consumed = min(food_before_consumption, food_consumption)

    if consumed:
        cur.execute("""
            UPDATE kingdoms
            SET food = GREATEST(0, food - %s)
            WHERE user_id = %s
        """, (consumed, user_id))

    if food_before_consumption < food_consumption:
        happiness = max(0, happiness - max(1, int(hours * 1.5)))
    else:
        happiness = min(100, happiness + int(hours * 0.15))

    growth_progress = float(population["growth_progress"])
    if (
        happiness >= 60
        and food_before_consumption >= food_consumption
        and population_count < housing_capacity
    ):
        growth_progress += hours / 24.0
        growth = min(
            housing_capacity - population_count,
            int(growth_progress)
        )
        if growth > 0:
            cur.execute("""
                UPDATE kingdoms SET population = population + %s
                WHERE user_id = %s
            """, (growth, user_id))
            growth_progress -= growth

    cur.execute(
        "UPDATE kingdoms SET happiness = %s WHERE user_id = %s",
        (happiness, user_id)
    )
    cur.execute("""
        UPDATE kingdom_population
        SET happiness = %s,
            housing_capacity = %s,
            growth_progress = %s,
            last_tick = %s
        WHERE user_id = %s
    """, (happiness, housing_capacity, growth_progress, now, user_id))

    for profession, worked_hours, produced in history:
        cur.execute("""
            INSERT INTO kingdom_production_history
                (user_id, profession, hours, produced)
            VALUES (%s, %s, %s, %s::jsonb)
        """, (
            user_id, profession, worked_hours,
            __import__("json").dumps(produced)
        ))

    event_text = None
    if active_event is None:
        event_chance = 1.0 - ((1.0 - 0.08) ** hours)
        if random.random() < event_chance:
            new_event = _new_event(cur, user_id, now)
            event_text = new_event["event_name"]

    return {
        "hours": hours,
        "gains": gains,
        "consumed": consumed,
        "happiness": happiness,
        "event": event_text,
        "housing": housing_capacity,
    }


def _get_state(user_id):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kingdoms WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            kingdom = cur.fetchone()
            if kingdom is None:
                return None

            tick = _advance(cur, user_id, kingdom)

            cur.execute("SELECT * FROM kingdoms WHERE user_id = %s", (user_id,))
            kingdom = cur.fetchone()
            cur.execute(
                "SELECT * FROM kingdom_population WHERE user_id = %s",
                (user_id,)
            )
            population = cur.fetchone()
            cur.execute("""
                SELECT profession, workers, xp, level, fatigue
                FROM kingdom_workers
                WHERE user_id = %s
                ORDER BY profession
            """, (user_id,))
            workers = cur.fetchall()
            cur.execute("""
                SELECT resource, amount
                FROM kingdom_extra_resources
                WHERE user_id = %s
                ORDER BY resource
            """, (user_id,))
            extra = {row["resource"]: int(row["amount"]) for row in cur.fetchall()}
            cur.execute("""
                SELECT technology, level
                FROM kingdom_technologies
                WHERE user_id = %s
                ORDER BY technology
            """, (user_id,))
            technologies = cur.fetchall()
            cur.execute("""
                SELECT event_name, description, expires_at
                FROM kingdom_active_events
                WHERE user_id = %s AND expires_at > CURRENT_TIMESTAMP
            """, (user_id,))
            event = cur.fetchone()

            return {
                "kingdom": kingdom,
                "population": population,
                "workers": workers,
                "extra": extra,
                "technologies": technologies,
                "event": event,
                "tick": tick,
            }


def _change_workers(user_id, profession, amount, assign):
    if profession not in JOBS:
        return "profession", None

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kingdoms WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            kingdom = cur.fetchone()
            if kingdom is None:
                return "missing", None

            _advance(cur, user_id, kingdom)

            cur.execute(
                "SELECT population FROM kingdoms WHERE user_id = %s",
                (user_id,)
            )
            population_count = int(cur.fetchone()["population"])

            cur.execute("""
                SELECT COALESCE(SUM(workers), 0) AS total
                FROM kingdom_workers WHERE user_id = %s
            """, (user_id,))
            assigned_total = int(cur.fetchone()["total"])

            cur.execute("""
                SELECT workers FROM kingdom_workers
                WHERE user_id = %s AND profession = %s
                FOR UPDATE
            """, (user_id, profession))
            row = cur.fetchone()
            current = int(row["workers"]) if row else 0

            if assign:
                available = population_count - assigned_total
                if amount > available:
                    return "population", available
                new_count = current + amount
            else:
                if amount > current:
                    return "workers", current
                new_count = current - amount

            cur.execute("""
                UPDATE kingdom_workers SET workers = %s
                WHERE user_id = %s AND profession = %s
            """, (new_count, user_id, profession))
            return "ok", new_count


def _research(user_id, technology):
    if technology not in TECHNOLOGIES:
        return "invalid", None

    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM kingdoms WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            kingdom = cur.fetchone()
            if kingdom is None:
                return "missing", None

            _advance(cur, user_id, kingdom)

            cur.execute("""
                SELECT level FROM kingdom_technologies
                WHERE user_id = %s AND technology = %s
                FOR UPDATE
            """, (user_id, technology))
            row = cur.fetchone()
            current_level = int(row["level"]) if row else 0

            if current_level >= 10:
                return "max", current_level

            next_level = current_level + 1
            research_cost = 100 * next_level
            gold_cost = 150 * next_level

            cur.execute("""
                SELECT gold FROM players WHERE user_id = %s FOR UPDATE
            """, (user_id,))
            player = cur.fetchone()
            if player is None or int(player["gold"]) < gold_cost:
                return "gold", gold_cost

            cur.execute("""
                UPDATE kingdom_extra_resources
                SET amount = amount - %s
                WHERE user_id = %s
                    AND resource = 'research_points'
                    AND amount >= %s
                RETURNING amount
            """, (research_cost, user_id, research_cost))
            if cur.fetchone() is None:
                return "research", research_cost

            cur.execute("""
                UPDATE players SET gold = gold - %s
                WHERE user_id = %s
            """, (gold_cost, user_id))
            cur.execute("""
                INSERT INTO kingdom_technologies (user_id, technology, level)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, technology)
                DO UPDATE SET level = EXCLUDED.level
            """, (user_id, technology, next_level))

            return "ok", (next_level, research_cost, gold_cost)


async def _error(interaction, command_name, error):
    print(f"[ERROR] kingdom {command_name}: {error!r}", flush=True)
    message = "Có lỗi khi xử lý Kingdom. Hãy kiểm tra log bot."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def population(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        kingdom = state["kingdom"]
        pop = state["population"]
        assigned = sum(int(row["workers"]) for row in state["workers"])
        available = max(0, int(kingdom["population"]) - assigned)

        embed = discord.Embed(
            title=f"👥 Dân số — {kingdom['name']}",
            color=discord.Color.green()
        )
        embed.add_field(name="Population", value=f"{kingdom['population']:,}")
        embed.add_field(name="Available Workers", value=f"{available:,}")
        embed.add_field(name="Working Population", value=f"{assigned:,}")
        embed.add_field(
            name="Housing",
            value=f"{kingdom['population']:,}/{pop['housing_capacity']:,}"
        )
        embed.add_field(name="Happiness", value=f"{pop['happiness']}/100")
        embed.add_field(name="Food", value=f"{kingdom['food']:,}")
        embed.add_field(
            name="Food consumption",
            value=f"{FOOD_PER_PERSON_HOUR:.2f} Food/người/giờ"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as error:
        await _error(interaction, "population", error)


async def workers(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        lines = []
        for row in state["workers"]:
            lines.append(
                f"{JOBS[row['profession']][0]}: **{row['workers']:,}** "
                f"· Lv.{row['level']} · XP {row['xp']:,} "
                f"· Fatigue {float(row['fatigue']):.1f}%"
            )
        await interaction.followup.send(
            "**🧑‍🌾 Workforce**\n" + "\n".join(lines),
            ephemeral=True
        )
    except Exception as error:
        await _error(interaction, "workers", error)


async def assign(interaction: discord.Interaction, profession: app_commands.Choice[str], amount: app_commands.Range[int, 1, 100000]):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        status, value = await asyncio.to_thread(
            _change_workers, interaction.user.id, profession.value, amount, True
        )
        if status == "missing":
            message = "Bạn chưa có vương quốc. Dùng `/kingdom create`."
        elif status == "population":
            message = f"Chỉ còn **{value:,}** dân chưa được phân công."
        else:
            message = (
                f"✅ Đã phân công **{amount:,}** dân vào "
                f"{JOBS[profession.value][0]}. Tổng: **{value:,}**."
            )
        await interaction.followup.send(message, ephemeral=True)
    except Exception as error:
        await _error(interaction, "assign", error)


async def unassign(interaction: discord.Interaction, profession: app_commands.Choice[str], amount: app_commands.Range[int, 1, 100000]):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        status, value = await asyncio.to_thread(
            _change_workers, interaction.user.id, profession.value, amount, False
        )
        if status == "missing":
            message = "Bạn chưa có vương quốc. Dùng `/kingdom create`."
        elif status == "workers":
            message = f"Nghề này hiện chỉ có **{value:,}** công nhân."
        else:
            message = (
                f"✅ Đã thu hồi **{amount:,}** công nhân khỏi "
                f"{JOBS[profession.value][0]}. Còn lại: **{value:,}**."
            )
        await interaction.followup.send(message, ephemeral=True)
    except Exception as error:
        await _error(interaction, "unassign", error)


async def farming(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            message = "Bạn chưa có vương quốc. Dùng `/kingdom create`."
        else:
            tick = state["tick"]
            if tick["hours"] <= 0:
                message = "⏳ Chưa có sản lượng mới kể từ lần cập nhật gần nhất."
            else:
                lines = [
                    f"{RESOURCE_LABELS.get(key, key)}: **+{value:,}**"
                    for key, value in tick["gains"].items()
                ]
                message = (
                    f"🌾 Đã xử lý **{tick['hours']:.2f} giờ** ngoại tuyến.\n"
                    + ("\n".join(lines) if lines else "Không có sản lượng.")
                )
                message += f"\n🍞 Food tiêu thụ: **-{tick['consumed']:,}**"
                message += f"\n😊 Happiness: **{tick['happiness']}/100**"
                if tick["event"]:
                    message += f"\n🌪️ Sự kiện mới: **{tick['event']}**"
        await interaction.followup.send(message, ephemeral=True)
    except Exception as error:
        await _error(interaction, "farming", error)


async def production(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        lines = []
        for row in state["workers"]:
            count = int(row["workers"])
            if count:
                outputs = ", ".join(
                    f"{RESOURCE_LABELS.get(key, key)} {count * rate:.1f}/giờ"
                    for key, rate in JOBS[row["profession"]][1].items()
                )
                lines.append(f"{JOBS[row['profession']][0]}: {outputs}")

        await interaction.followup.send(
            "**📈 Sản lượng cơ bản (chưa tính bonus)**\n"
            + ("\n".join(lines) if lines else "Chưa phân công công nhân."),
            ephemeral=True
        )
    except Exception as error:
        await _error(interaction, "production", error)


async def resources(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        kingdom = state["kingdom"]
        values = {
            "food": kingdom["food"],
            "wood": kingdom["wood"],
            "stone": kingdom["stone"],
            "iron": kingdom["iron"],
            **state["extra"],
        }
        lines = [
            f"{RESOURCE_LABELS.get(key, key)}: **{value:,}**"
            for key, value in values.items()
        ]
        await interaction.followup.send(
            "**📦 Kho tài nguyên Kingdom**\n" + "\n".join(lines),
            ephemeral=True
        )
    except Exception as error:
        await _error(interaction, "resources", error)


async def buildings(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        with database.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT building_key, level
                    FROM kingdom_buildings
                    WHERE user_id = %s
                    ORDER BY building_key
                """, (interaction.user.id,))
                rows = cur.fetchall()

        lines = [
            f"**{row['building_key'].replace('_', ' ').title()}**: Lv.{row['level']}"
            for row in rows
        ]
        await interaction.followup.send(
            "**🏗️ Công trình Kingdom**\n"
            + ("\n".join(lines) if lines else "Chưa có công trình."),
            ephemeral=True
        )
    except Exception as error:
        await _error(interaction, "buildings", error)


async def technology(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        levels = {
            row["technology"]: int(row["level"])
            for row in state["technologies"]
        }
        lines = [
            f"**{name}** — Lv.{levels.get(key, 0)}/10\n{description}"
            for key, (name, description) in TECHNOLOGIES.items()
        ]
        await interaction.followup.send(
            "**🔬 Kingdom Technology**\n" + "\n".join(lines),
            ephemeral=True
        )
    except Exception as error:
        await _error(interaction, "technology", error)


async def research(interaction: discord.Interaction, technology: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        status, value = await asyncio.to_thread(
            _research, interaction.user.id, technology.value
        )
        if status == "missing":
            message = "Bạn chưa có vương quốc. Dùng `/kingdom create`."
        elif status == "max":
            message = "Công nghệ đã đạt cấp tối đa 10."
        elif status == "gold":
            message = f"Không đủ Gold. Cần **{value:,} Gold**."
        elif status == "research":
            message = f"Không đủ Research Points. Cần **{value:,} điểm**."
        elif status == "invalid":
            message = "Công nghệ không hợp lệ."
        else:
            level, points, gold = value
            message = (
                f"🔬 Đã nghiên cứu **{technology.name} cấp {level}**!\n"
                f"Chi phí: {points:,} Research Points và {gold:,} Gold."
            )
        await interaction.followup.send(message, ephemeral=True)
    except Exception as error:
        await _error(interaction, "research", error)


async def event(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        state = await asyncio.to_thread(_get_state, interaction.user.id)
        if state is None:
            await interaction.followup.send(
                "Bạn chưa có vương quốc. Dùng `/kingdom create`.",
                ephemeral=True
            )
            return

        active = state["event"]
        if active is None:
            message = "Hiện tại vương quốc không có sự kiện đang diễn ra."
        else:
            remaining = max(
                0,
                int((active["expires_at"] - datetime.now(timezone.utc)).total_seconds() // 60)
            )
            message = (
                f"🌪️ **{active['event_name']}**\n"
                f"{active['description']}\n"
                f"Còn khoảng **{remaining} phút**."
            )
        await interaction.followup.send(message, ephemeral=True)
    except Exception as error:
        await _error(interaction, "event", error)


def _choices():
    return [
        app_commands.Choice(name=JOBS[key][0], value=key)
        for key in JOBS
    ]


def _technology_choices():
    return [
        app_commands.Choice(name=value[0], value=key)
        for key, value in TECHNOLOGIES.items()
    ]


async def setup(bot):
    # commands.kingdom must be loaded first because it owns the /kingdom group.
    await asyncio.to_thread(ensure_schema)
    group = bot.tree.get_command("kingdom")
    if group is None:
        raise RuntimeError(
            "Không tìm thấy /kingdom. Hãy load commands.kingdom trước "
            "commands.kingdom_management."
        )

    commands_to_add = [
        app_commands.Command(name="population", description="Xem dân số và dân sinh", callback=population),
        app_commands.Command(name="workers", description="Xem công nhân và chuyên môn", callback=workers),
        app_commands.Command(
            name="assign", description="Phân công dân vào nghề",
            callback=assign, choices={"profession": _choices()}
        ),
        app_commands.Command(
            name="unassign", description="Thu hồi công nhân khỏi nghề",
            callback=unassign, choices={"profession": _choices()}
        ),
        app_commands.Command(name="farming", description="Thu hoạch sản lượng ngoại tuyến", callback=farming),
        app_commands.Command(name="production", description="Xem tốc độ sản xuất", callback=production),
        app_commands.Command(name="resources", description="Xem kho tài nguyên", callback=resources),
        app_commands.Command(name="buildings", description="Xem công trình Kingdom", callback=buildings),
        app_commands.Command(name="technology", description="Xem cây công nghệ", callback=technology),
        app_commands.Command(
            name="research", description="Nghiên cứu công nghệ",
            callback=research, choices={"technology": _technology_choices()}
        ),
        app_commands.Command(name="event", description="Xem sự kiện Kingdom", callback=event),
    ]

    for command in commands_to_add:
        if group.get_command(command.name) is None:
            group.add_command(command)

    print("Loaded: kingdom management", flush=True)
