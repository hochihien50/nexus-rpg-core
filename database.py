import sqlite3
from pathlib import Path

DB_PATH = Path("data/game.db")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                gold INTEGER NOT NULL DEFAULT 500,
                gems INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                exp INTEGER NOT NULL DEFAULT 0,
                hp INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                daily_at TEXT,
                work_at TEXT
            )
        """)

def get_player(user_id):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()

def ensure_player(user_id, username):
    with connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO players (user_id, username)
            VALUES (?, ?)
        """, (user_id, username))
        conn.execute(
            "UPDATE players SET username = ? WHERE user_id = ?",
            (username, user_id)
        )
    return get_player(user_id)

def update_player(user_id, **fields):
    allowed = {"gold", "gems", "level", "exp", "hp", "daily_at", "work_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [user_id]
    with connect() as conn:
        conn.execute(
            f"UPDATE players SET {columns} WHERE user_id = ?", values
        )
