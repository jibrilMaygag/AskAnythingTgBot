"""
states.py – Conversation state constants and in-memory state storage.

State storage uses simple dicts (user_id → value).
For multi-instance deployments, replace with Redis or DB-backed sessions.
"""

# ── Profile ───────────────────────────────────────────────────────────────────
IDLE                    = "IDLE"
SETTING_NAME            = "SETTING_NAME"
SETTING_GENDER          = "SETTING_GENDER"
# SETTING_IMAGE removed — profile-picture functionality disabled

# ── Question flow ─────────────────────────────────────────────────────────────
CHOOSING_TOPIC          = "CHOOSING_TOPIC"
WRITING_QUESTION        = "WRITING_QUESTION"
WRITING_QUESTION_IMAGE  = "WRITING_QUESTION_IMAGE"
CONFIRMING_QUESTION     = "CONFIRMING_QUESTION"

# ── Reply flow ────────────────────────────────────────────────────────────────
WRITING_REPLY           = "WRITING_REPLY"
WRITING_REPLY_IMAGE     = "WRITING_REPLY_IMAGE"

# ── Navigation ────────────────────────────────────────────────────────────────
VIEWING_QUESTION        = "VIEWING_QUESTION"

# ── Search ────────────────────────────────────────────────────────────────────
SEARCHING               = "SEARCHING"

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_BAN_INPUT         = "ADMIN_BAN_INPUT"
ADMIN_MUTE_INPUT        = "ADMIN_MUTE_INPUT"

# ── In-memory session stores ──────────────────────────────────────────────────
user_state: dict[int, str] = {}   # user_id → current state constant
user_data: dict[int, dict] = {}   # user_id → arbitrary context payload
