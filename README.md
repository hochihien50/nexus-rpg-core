# NEXUS RPG - Core 1.0

Discord bot starter with:
- `/profile`
- `/balance`
- `/daily` (24-hour cooldown)
- `/work` (5-minute cooldown)
- `/nuke` (60-second Discord timeout; no custom moderation log)

## Local setup
1. Install Python 3.12+
2. Run `python -m venv venv`
3. Activate: `venv\Scripts\activate` (Windows)
4. Run `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`
6. Run `python main.py`

Invite scopes: `bot`, `applications.commands`.
Bot permission: `Moderate Members` for `/nuke`.

SQLite database is created at `data/game.db`.
For Render, use a persistent disk mounted at `/var/data` and update
`DB_PATH` in `database.py` to `Path("/var/data/game.db")`.
