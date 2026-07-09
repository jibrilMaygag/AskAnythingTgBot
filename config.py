"""
config.py – Central configuration loaded from environment variables.
Copy .env.example to .env and fill in your values.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TOKEN: str = os.getenv("BOT_TOKEN", "")
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "YourBotUsername")   # without @
CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "@YourChannel")
CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "0"))               # numeric ID

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_IDS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip().isdigit()
]

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("DB_NAME", "askanything")

# ── Pagination ────────────────────────────────────────────────────────────────
REPLIES_PER_PAGE: int = 10
SEARCH_PER_PAGE: int = 8
LEADERBOARD_PER_PAGE: int = 10
TRENDING_PER_PAGE: int = 5

# ── Reputation weights ────────────────────────────────────────────────────────
REP_UPVOTE_RECEIVED: int = 5
REP_DOWNVOTE_RECEIVED: int = -2
REP_ANSWER_POSTED: int = 1
REP_QUESTION_POSTED: int = 1
