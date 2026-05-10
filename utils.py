from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from datetime import datetime
from database import get_user, get_question, get_replies_for_question, get_user_vote
from config import BOT_USERNAME, CHANNEL_USERNAME


# ============= TIME FORMATTING =============
def time_ago(iso_timestamp: str) -> str:
    """Convert ISO timestamp to 'X time ago' format."""
    try:
        created = datetime.fromisoformat(iso_timestamp)
        now = datetime.now()
        delta = now - created
        
        seconds = delta.total_seconds()
        
        if seconds < 60:
            return f"{int(seconds)}s ago"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m ago"
        elif seconds < 86400:
            return f"{int(seconds / 3600)}h ago"
        elif seconds < 604800:
            return f"{int(seconds / 86400)}d ago"
        else:
            return f"{int(seconds / 604800)}w ago"
    except:
        return "now"


# ============= USER FORMATTING =============
def get_user_display(user_id: int) -> str:
    """Get formatted user display: emoji + name or 'Anonymous'."""
    user = get_user(user_id)
    
    if not user:
        return "Anonymous"
    
    display_name = user.get("display_name") or "Anonymous"
    gender = user.get("gender")
    
    emoji = ""
    if gender == "M":
        emoji = "👨 "
    elif gender == "F":
        emoji = "👩 "
    
    return f"{display_name}{emoji}"


# ============= KEYBOARD BUILDERS =============
def build_main_menu():
    """Build main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("✍️ Ask Question", callback_data="ask")],
        [InlineKeyboardButton("🔍 Search", callback_data="search")],
        [InlineKeyboardButton("🔥 Trending", callback_data="trending")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_topic_keyboard():
    """Build topic selection keyboard."""
    keyboard = [
        [InlineKeyboardButton("🎓 Education", callback_data="topic_edu")],
        [InlineKeyboardButton("💻 Tech", callback_data="topic_tech")],
        [InlineKeyboardButton("❤️ Life", callback_data="topic_life")],
        [InlineKeyboardButton("🌍 General", callback_data="topic_general")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_confirm_keyboard():
    """Build confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_question"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_question"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_reply_keyboard(reply_id: str, question_id: str, user_id: int = None):
    """Build keyboard for a reply with voting and action buttons."""
    reply_data = __import__("database").get_reply(reply_id)
    
    if not reply_data:
        return InlineKeyboardMarkup([])
    
    upvotes = reply_data.get("upvotes", 0)
    downvotes = reply_data.get("downvotes", 0)
    
    # Determine current user's vote if user_id provided
    user_vote = None
    if user_id:
        user_vote = get_user_vote(reply_id, user_id)
    
    # Vote buttons
    up_emoji = "👍" if user_vote != "up" else "👍✓"
    down_emoji = "👎" if user_vote != "down" else "👎✓"
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"{up_emoji} {upvotes}",
                callback_data=f"vote_up:{reply_id}:{question_id}"
            ),
            InlineKeyboardButton(
                f"{down_emoji} {downvotes}",
                callback_data=f"vote_down:{reply_id}:{question_id}"
            ),
            InlineKeyboardButton(
                "💬 Reply",
                callback_data=f"reply_to_reply:{reply_id}:{question_id}"
            ),
            InlineKeyboardButton(
                "🚩 Report",
                callback_data=f"report:{reply_id}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_show_more_keyboard(question_id: str, offset: int, total: int):
    """Build 'Show More' / 'Show All' keyboard."""
    keyboard = []
    
    if offset < total:
        if offset + 10 < total:
            keyboard.append([
                InlineKeyboardButton(
                    "📥 Show More (10)",
                    callback_data=f"show_more:{question_id}:{offset}"
                ),
                InlineKeyboardButton(
                    "📖 Show All",
                    callback_data=f"show_all:{question_id}:{offset}"
                ),
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    "📖 Show All",
                    callback_data=f"show_all:{question_id}:{offset}"
                ),
            ])
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None


def build_profile_setup_keyboard():
    """Build keyboard for profile setup."""
    keyboard = [
        [
            InlineKeyboardButton("👨 Male", callback_data="gender_M"),
            InlineKeyboardButton("👩 Female", callback_data="gender_F"),
            InlineKeyboardButton("⭕ Skip", callback_data="gender_skip"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_channel_question_keyboard(question_id: str):
    """Build keyboard for questions posted to channel."""
    question = get_question(question_id)
    if not question:
        return InlineKeyboardMarkup([])
    
    reply_count = question.get("reply_count", 0)
    
    # Answer button
    keyboard = [
        [
            InlineKeyboardButton(
                "✍️ Answer",
                url=f"https://t.me/{BOT_USERNAME}?start=answer_{question_id}"
            ),
        ]
    ]
    
    # Add Answers button only if there are replies
    if reply_count > 0:
        keyboard[0].append(
            InlineKeyboardButton(
                f"💬 Answers ({reply_count})",
                url=f"https://t.me/{BOT_USERNAME}?start=show_{question_id}"
            )
        )
    
    return InlineKeyboardMarkup(keyboard)


# ============= MESSAGE RENDERING =============
def format_question(question_id: str) -> str:
    """Format question for display."""
    question = get_question(question_id)
    if not question:
        return "❌ Question not found"
    
    user_display = get_user_display(question["user_id"])
    timestamp = time_ago(question["created_at"])
    
    return (
        f"#{question['topic']}\n\n"
        f"{question['text']}"
        f"\n\nBy: {user_display}"
    )


def format_reply(reply_id: str) -> str:
    """Format reply for display."""
    reply = __import__("database").get_reply(reply_id)
    if not reply:
        return "❌ Reply not found"
    
    user_display = get_user_display(reply["user_id"])
    timestamp = time_ago(reply["created_at"])
    
    return (
        f"{reply['text']}"
        f"\n\nBy:{user_display} 🎖 {166} rep \n {timestamp}"
    )


def format_reply_stats(reply_id: str) -> str:
    """Format reply with vote counts."""
    reply = __import__("database").get_reply(reply_id)
    if not reply:
        return ""
    
    upvotes = reply.get("upvotes", 0)
    downvotes = reply.get("downvotes", 0)
    
    return f"\n\n👍 {upvotes} | 👎 {downvotes}"


# ============= MESSAGE SENDING =============
async def send_question(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    question_id: str,
    user_id: int = None,
) -> int:
    """Send question message to chat. Returns message_id."""
    text = format_question(question_id)
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML"
    )
    
    return msg.message_id


async def send_reply(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    reply_id: str,
    question_id: str,
    user_id: int = None,
    reply_to_message_id: int = None,
) -> int:
    """Send reply message to chat. Returns message_id."""
    text = format_reply(reply_id) 
    keyboard = build_reply_keyboard(reply_id, question_id, user_id)
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        reply_to_message_id=reply_to_message_id,
        parse_mode="HTML"
    )
    
    return msg.message_id


async def send_replies_batch(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    question_id: str,
    count: int = 10,
    offset: int = 0,
    user_id: int = None,
) -> tuple:
    """
    Send a batch of replies for a question.
    Returns (messages_sent, total_replies).
    """
    replies = get_replies_for_question(question_id)
    total = len(replies)
    
    # Get subset
    batch = replies[offset:offset + count]
    
    messages_sent = 0
    for reply in batch:
        try:
            await send_reply(
                context,
                chat_id,
                reply["id"],
                question_id,
                user_id
            )
            messages_sent += 1
        except Exception as e:
            print(f"Error sending reply {reply['id']}: {e}")
    
    return messages_sent, total


async def update_reply_vote_display(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    reply_id: str,
    question_id: str,
    user_id: int = None,
):
    """Update a reply message's vote counts and buttons in-place."""
    try:
        keyboard = build_reply_keyboard(reply_id, question_id, user_id)
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Error updating reply display: {e}")
