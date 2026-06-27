"""
utils.py – Reusable helpers: rendering, keyboard builders, time formatting, send helpers.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from config import (
    BOT_USERNAME, CHANNEL_USERNAME,
    REPLIES_PER_PAGE, TRENDING_PER_PAGE, LEADERBOARD_PER_PAGE,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# TIME FORMATTING
# ═════════════════════════════════════════════════════════════════════════════

def time_ago(dt: datetime) -> str:
    """Return a human-friendly relative time string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (now - dt).total_seconds()

    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    if delta < 604800:
        return f"{int(delta / 86400)}d ago"
    return f"{int(delta / 604800)}w ago"


# ═════════════════════════════════════════════════════════════════════════════
# USER DISPLAY
# ═════════════════════════════════════════════════════════════════════════════

def gender_emoji(gender: Optional[str]) -> str:
    return {"M": "👨 ", "F": "👩 "}.get(gender, "")


def format_user_display(user: dict) -> str:
    """👨 John • 🎖 778 rep  — or —  Anonymous 🎖 0 rep"""
    if not user:
        return "Anonymous 🎖 0 rep"
    name = user.get("display_name") or "Anonymous"
    gender = user.get("gender")
    rep = user.get("reputation", 0)
    emoji = gender_emoji(gender)
    return f"{emoji}{name} 🎖 {rep} rep"


def format_user_short(user: dict) -> str:
    """👨 John  — without rep, for compact contexts."""
    if not user:
        return "Anonymous"
    name = user.get("display_name") or "Anonymous"
    emoji = gender_emoji(user.get("gender"))
    return f"{emoji}{name}"


# ═════════════════════════════════════════════════════════════════════════════
# CONTENT FORMATTING
# ═════════════════════════════════════════════════════════════════════════════

def format_question_text(question: dict, author: dict) -> str:
    topic = question.get("topic", "general").lower()
    author_name = format_user_short(author or {})
    return (
        f"#{topic}\n\n"
        f"<b>{question['text']}</b>\n\n"
        f"By: {author_name}"
    )


def format_reply_text(reply: dict, author: dict) -> str:
    ts = time_ago(reply["created_at"])
    user_line = format_user_display(author)
    text = reply.get("text", "")
    return (
        f"<b>{text}</b>\n\n"
        f"By: {user_line}\n" 
        f"{ts}"
    )


def format_profile_text(user: dict) -> str:
    name = format_user_short(user or {})
    gender = {"M": "👨 Male", "F": "👩 Female"}.get(user.get("gender"), "Not set")
    rep = user.get("reputation", 0)
    questions = len(user.get("question_ids", []))
    replies = len(user.get("reply_ids", []))
    joined = time_ago(user.get("created_at", datetime.now(timezone.utc)))
    return (
        f"👤 <b>Profile</b>\n\n"
        f"Name: <b>{name}</b>\n"
        f"Gender: {gender}\n"
        f"Reputation: 🎖 <b>{rep}</b>\n"
        f"Questions: {questions}\n"
        f"Answers: {replies}\n"
        f"Joined: {joined}"
    )


def oid(doc: dict) -> str:
    """Return string representation of _id."""
    return str(doc["_id"])


# ═════════════════════════════════════════════════════════════════════════════
# KEYBOARD BUILDERS
# ═════════════════════════════════════════════════════════════════════════════

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Ask Question", callback_data="ask")],
        [
            InlineKeyboardButton("🔍 Search", callback_data="search"),
            InlineKeyboardButton("🔥 Trending", callback_data="trending:0"),
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard:0"),
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
        ],
    ])


def kb_topic() -> InlineKeyboardMarkup:
    topics = [
        "Art", "Beauty", "Business", "Education", "Entertainment",
        "Family", "Food", "Health", "History", "Language",
        "Law", "Personal", "Philosophy", "Politics", "Relationships",
        "Religion", "Science", "Sexual", "Society", "Sport",
        "Technology", "Other",
    ]
    # Build two-column keyboard of topics (title-cased labels, callback uses lowercase)
    rows = []
    for i in range(0, len(topics), 2):
        left = topics[i]
        right = topics[i + 1] if i + 1 < len(topics) else None
        if right:
            rows.append([
                InlineKeyboardButton(left, callback_data=f"topic_{left.lower()}"),
                InlineKeyboardButton(right, callback_data=f"topic_{right.lower()}"),
            ])
        else:
            rows.append([InlineKeyboardButton(left, callback_data=f"topic_{left.lower()}")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def kb_confirm_question(has_image: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Post It", callback_data="confirm_question"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ]])


def kb_confirm_reply(has_image: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Post Reply", callback_data="confirm_reply"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ]])


def kb_profile() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change Name", callback_data="profile_set_name")],
        [InlineKeyboardButton("🚻 Set Gender", callback_data="profile_set_gender")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ])


def kb_gender(include_skip: bool = True) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton("👨 Male", callback_data="gender_M"),
        InlineKeyboardButton("👩 Female", callback_data="gender_F"),
    ]
    if include_skip:
        row.append(InlineKeyboardButton("⭕ Skip", callback_data="gender_skip"))
    return InlineKeyboardMarkup([row])


def kb_reply(
    reply_id: str,
    question_id: str,
    user_vote: Optional[str] = None,
    up_count: int = 0,
    dn_count: int = 0,
    is_flagged: bool = False,
) -> InlineKeyboardMarkup:
    flag_label = "🚩 Flagged" if is_flagged else "🚩"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"👍{'✓' if user_vote == 'up' else ''} {up_count}",
            callback_data=f"vote_up:{reply_id}:{question_id}"
        ),
        InlineKeyboardButton(
            f"👎{'✓' if user_vote == 'down' else ''} {dn_count}",
            callback_data=f"vote_down:{reply_id}:{question_id}"
        ),
        InlineKeyboardButton(flag_label, callback_data=f"report_reply:{reply_id}"),
        InlineKeyboardButton("💬 Reply", callback_data=f"reply_to:{reply_id}:{question_id}"),
    ]])


def kb_show_more(question_id: str, offset: int, total: int) -> Optional[InlineKeyboardMarkup]:
    if offset >= total:
        return None
    remaining = total - offset
    buttons = []
    if remaining > REPLIES_PER_PAGE:
        buttons.append(InlineKeyboardButton(
            f"📥 Show {REPLIES_PER_PAGE} More", callback_data=f"show_more:{question_id}:{offset}"
        ))
    buttons.append(InlineKeyboardButton(
        f"📖 Show All ({remaining})", callback_data=f"show_all:{question_id}:{offset}"
    ))
    return InlineKeyboardMarkup([buttons])


def kb_channel_question(question_id: str, reply_count: int) -> InlineKeyboardMarkup:
    """Keyboard attached to channel-posted question."""
    answer_url = f"https://t.me/{BOT_USERNAME}?start=answer_{question_id}"
    view_url = f"https://t.me/{BOT_USERNAME}?start=show_{question_id}"
    row = [InlineKeyboardButton("✍️ Answer", url=answer_url)]
    if reply_count > 0:
        row.append(InlineKeyboardButton(f"💬 {reply_count} Answers", url=view_url))
    return InlineKeyboardMarkup([row])


def kb_trending_nav(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"trending:{page - 1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"trending:{page + 1}"))
    rows = [buttons] if buttons else []
    rows.append([InlineKeyboardButton("🔙 Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def kb_leaderboard_nav(page: int, has_next: bool) -> InlineKeyboardMarkup:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"leaderboard:{page - 1}"))
    if has_next:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"leaderboard:{page + 1}"))
    rows = [buttons] if buttons else []
    rows.append([InlineKeyboardButton("🔙 Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def kb_search_nav(query: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    import urllib.parse
    q = urllib.parse.quote(query)
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"search_page:{q}:{page - 1}"))
    if has_next:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"search_page:{q}:{page + 1}"))
    rows = [buttons] if buttons else []
    rows.append([InlineKeyboardButton("🔙 Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def kb_admin_report(report_id: str, target_type: str, target_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Delete", callback_data=f"admin_delete:{target_type}:{target_id}:{report_id}"),
        InlineKeyboardButton("🔇 Mute Author", callback_data=f"admin_mute_from_report:{target_id}:{report_id}"),
        InlineKeyboardButton("✅ Dismiss", callback_data=f"admin_dismiss:{report_id}"),
    ]])


# ═════════════════════════════════════════════════════════════════════════════
# SEND HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def send_question_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    question: dict,
    author: dict,
) -> int:
    """Send a formatted question. Returns telegram message_id."""
    text = format_question_text(question, author)
    question_id = oid(question)
    reply_count = question.get("reply_count", 0)
    keyboard = kb_channel_question(question_id, reply_count)

    if question.get("image_file_id"):
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=question["image_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    return msg


async def send_reply_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    reply: dict,
    author: dict,
    question_id: str,
    viewer_id: int = None,
    reply_to_message_id: int = None,
) -> int:
    """Send a formatted reply. Returns telegram message_id."""
    text = format_reply_text(reply, author)
    reply_id = oid(reply)
    user_vote = None
    is_flagged = False
    if viewer_id:
        user_vote = await db.get_user_vote(reply["_id"], viewer_id)
        is_flagged = await db.has_report(reply["_id"], viewer_id)
    keyboard = kb_reply(
        reply_id,
        question_id,
        user_vote,
        up_count=reply.get("upvotes", 0),
        dn_count=reply.get("downvotes", 0),
        is_flagged=is_flagged,
    )

    kwargs = dict(chat_id=chat_id, parse_mode="HTML", reply_markup=keyboard)
    if reply_to_message_id:
        kwargs["reply_to_message_id"] = reply_to_message_id

    if reply.get("image_file_id"):
        msg = await context.bot.send_photo(
            photo=reply["image_file_id"],
            caption=text,
            **kwargs,
        )
    else:
        msg = await context.bot.send_message(text=text, **kwargs)

    return msg.message_id


async def send_replies_batch(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    question_id: str,
    offset: int = 0,
    limit: int = REPLIES_PER_PAGE,
    viewer_id: int = None,
    exclude_reply_id: str = None,
) -> tuple[int, int]:
    """Send a page of replies. Returns (sent_count, total)."""
    replies, total = await db.get_replies_for_question(
        question_id,
        offset=offset,
        limit=limit,
        exclude_reply_id=exclude_reply_id,
    )
    sent = 0
    for reply in replies:
        author = await db.get_user(reply["author_id"])
        try:
            # If this reply references a parent reply, try to set reply_to_message_id
            reply_to_msg_id = None
            parent_id = reply.get("parent_reply_id")
            if parent_id:
                parent = await db.get_reply(parent_id)
                if parent and parent.get("telegram_message_id") and parent.get("telegram_chat_id") == chat_id:
                    reply_to_msg_id = parent.get("telegram_message_id")

            msg_id = await send_reply_message(
                context, chat_id, reply, author or {}, question_id, viewer_id, reply_to_message_id=reply_to_msg_id
            )
            # Persist Telegram message id and chat id for this reply so future "reply-to" targets
            # can reference it and create native clickable reply links.
            try:
                await db.update_reply(oid(reply), telegram_message_id=msg_id, telegram_chat_id=chat_id)
            except Exception:
                logger.debug("Could not persist telegram_message_id for reply %s", reply.get("_id"))
            sent += 1
        except Exception as exc:
            logger.warning("Error sending reply %s: %s", reply["_id"], exc)
    return sent, total


async def update_reply_vote_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    reply_id: str,
    question_id: str,
    viewer_id: int = None,
) -> None:
    user_vote = None
    is_flagged = False
    if viewer_id:
        user_vote = await db.get_user_vote(reply_id, viewer_id)
        is_flagged = await db.has_report(reply_id, viewer_id)
    # We don't currently know the reply counts here, so refresh from DB if needed.
    reply = await db.get_reply(reply_id)
    keyboard = kb_reply(
        reply_id,
        question_id,
        user_vote,
        up_count=reply.get("upvotes", 0) if reply else 0,
        dn_count=reply.get("downvotes", 0) if reply else 0,
        is_flagged=is_flagged,
    )
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=keyboard
        )
    except Exception as exc:
        logger.warning("Could not update vote keyboard: %s", exc)
