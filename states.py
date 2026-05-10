"""
Conversation states for user interactions.
Format: user_state[user_id] = STATE_NAME
"""

# ============= MAIN STATES =============
IDLE = "IDLE"  # User is at main menu
CHOOSING_TOPIC = "CHOOSING_TOPIC"  # User selected "Ask Question"
WRITING_QUESTION = "WRITING_QUESTION"  # User typing question
CONFIRMING_QUESTION = "CONFIRMING_QUESTION"  # Question typed, awaiting confirm
SETTING_PROFILE = "SETTING_PROFILE"  # User setting display name
SETTING_GENDER = "SETTING_GENDER"  # User setting gender

# ============= REPLY STATES =============
WRITING_REPLY = "WRITING_REPLY"  # User typing reply to question
WRITING_REPLY_TO_REPLY = "WRITING_REPLY_TO_REPLY"  # User replying to a reply

# ============= VIEW STATES =============
VIEWING_QUESTION = "VIEWING_QUESTION"  # User viewing a question and its replies

# ============= STATE STORAGE =============
user_state = {}  # user_id -> current state
user_data = {}  # user_id -> {additional context data}