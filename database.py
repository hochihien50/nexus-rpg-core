
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def connect():
    if not DATABASE_URL:
        raise RuntimeError("Thieu DATABASE_URL trong Environment")

    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        connect_timeout=10
    )
    return conn

def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT NOT NULL,
                    gold BIGINT NOT NULL DEFAULT 500,
                    gems BIGINT NOT NULL DEFAULT 0,
                    level BIGINT NOT NULL DEFAULT 1,
                    exp BIGINT NOT NULL DEFAULT 0,
                    hp BIGINT NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    daily_at TEXT,
                    work_at TEXT
                )
            """)

def get_player(user_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM players WHERE user_id = %s",
                (user_id,)
            )
            return cur.fetchone()

def ensure_player(user_id, username):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO players (user_id, username)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, username))

            cur.execute(
                "UPDATE players SET username = %s WHERE user_id = %s",
                (username, user_id)
            )

    return get_player(user_id)

def update_player(user_id, **fields):
    allowed = {
        "gold",
        "gems",
        "level",
        "exp",
        "hp",
        "daily_at",
        "work_at"
    }

    fields = {
        k: v for k, v in fields.items()
        if k in allowed
    }

    if not fields:
        return

    columns = ", ".join(
        f"{key} = %s" for key in fields
    )

    values = list(fields.values()) + [user_id]

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE players SET {columns} WHERE user_id = %s",
                values
            )
