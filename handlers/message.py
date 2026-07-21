"""
messages.py – Handles all incoming user messages (text + photos).

State machine:
  SETTING_NAME           → save display name
  SETTING_GENDER         → (handled via buttons)
  WRITING_QUESTION       → collect question text, optionally await image
  WRITING_QUESTION_IMAGE → collect optional question photo
  WRITING_REPLY          → collect reply text, optionally await image
  WRITING_REPLY_IMAGE    → collect optional reply photo
  SEARCHING              → run search query
  IDLE / anything else   → show main menu hint
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import notifications
from config import CHANNEL_USERNAME, REPLIES_PER_PAGE
from logging_utils import log_event
from states import (
    user_state, user_data,
    IDLE, SETTING_NAME,
    WRITING_QUESTION, WRITING_QUESTION_IMAGE,
    WRITING_REPLY, WRITING_REPLY_IMAGE,
    SEARCHING,
)
from utils import (
    kb_main_menu, kb_confirm_question, kb_confirm_reply,
    kb_show_more, kb_search_nav,
    send_question_message, send_reply_message, send_replies_batch,
    format_question_text, format_reply_text,
    oid, SimpleRateLimiter, sanitize_text_content, validate_topic,
)

logger = logging.getLogger(__name__)

QUESTION_RATE_LIMITER = SimpleRateLimiter(limit=3, window_seconds=60)
REPLY_RATE_LIMITER = SimpleRateLimiter(limit=8, window_seconds=60)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN DISPATCH
# ═════════════════════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    msg = update.message

    # Resolve text vs photo
    text = msg.text or msg.caption or ""
    photo = msg.photo[-1] if msg.photo else None

    user = await db.get_or_create_user(user_id)

    if user.get("is_banned"):
        await msg.reply_text("🚫 You are banned.")
        return

    if _is_muted(user):
        await msg.reply_text("🔇 You are muted.")
        return

    state = user_state.get(user_id, IDLE)

    # ── Profile name ───────────────────────────────────────────────────────
    if state == SETTING_NAME:
        await _handle_set_name(update, context, user_id, text)
        return

    # ── Question flow ──────────────────────────────────────────────────────
    if state == WRITING_QUESTION:
        await _handle_question_text(update, context, user_id, text, photo)
        return

    if state == WRITING_QUESTION_IMAGE:
        if photo:
            user_data[user_id]["image_file_id"] = photo.file_id
        await _send_question_preview(update, context, user_id)
        return

    # ── Reply flow ─────────────────────────────────────────────────────────
    if state == WRITING_REPLY:
        await _handle_reply_text(update, context, user_id, text, photo)
        return

    if state == WRITING_REPLY_IMAGE:
        if photo:
            user_data[user_id]["image_file_id"] = photo.file_id
        await _send_reply_preview(update, context, user_id)
        return

    # ── Search ─────────────────────────────────────────────────────────────
    if state == SEARCHING:
        await _handle_search(update, context, user_id, chat_id, text)
        return

    # ── Fallback ───────────────────────────────────────────────────────────
    await msg.reply_text(
        "Use /start or tap a button to navigate.",
        reply_markup=kb_main_menu(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# PROFILE
# ═════════════════════════════════════════════════════════════════════════════

async def _handle_set_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str
) -> None:
    cleaned = sanitize_text_content(text, max_length=32)
    if not cleaned or len(cleaned) > 32:
        await update.message.reply_text("❗ Name must be 1-32 characters. Try again:")
        return
    await db.update_user(user_id, display_name=cleaned)
    user_state[user_id] = IDLE
    await update.message.reply_text(
        f"✅ Display name set to <b>{text}</b>!",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# QUESTION
# ═════════════════════════════════════════════════════════════════════════════

async def _handle_question_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    photo,
) -> None:
    cleaned_text = sanitize_text_content(text, max_length=3000)
    if not cleaned_text:
        await update.message.reply_text("❗ Please write your question text.")
        return
    if not QUESTION_RATE_LIMITER.allow(str(user_id), "question"):
        await update.message.reply_text("⏳ You are sending questions too quickly. Please wait a moment.")
        return

    user_data.setdefault(user_id, {})
    user_data[user_id]["question_text"] = cleaned_text
    if photo:
        user_data[user_id]["image_file_id"] = photo.file_id
        await _send_question_preview(update, context, user_id)
    else:
        await _send_question_preview(update, context, user_id)


async def _send_question_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> None:
    data = user_data.get(user_id, {})
    topic = data.get("topic", "general")
    text = data.get("question_text", "")

    preview = (
        f"<b>Preview your question:</b>\n\n"
        f"<b>#{topic.upper()}</b>\n\n"
        f"{text}"
    )
    await update.message.reply_text(
        preview,
        parse_mode="HTML",
        reply_markup=kb_confirm_question(),
    )


async def post_question_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> None:
    """Save question to DB as pending for admin review."""
    data = user_data.get(user_id, {})
    topic = data.get("topic", "general")
    text = sanitize_text_content(data.get("question_text", ""), max_length=3000)
    image_file_id = data.get("image_file_id")

    if not text or not validate_topic(topic):
        return None

    question = await db.create_question(user_id, topic, text, image_file_id)
    log_event("question_submitted", user_id, {"topic": topic, "question_id": str(question.get("_id", ""))})

    # Cleanup
    user_state.pop(user_id, None)
    user_data.pop(user_id, None)
    return question


# ═════════════════════════════════════════════════════════════════════════════
# REPLY
# ═════════════════════════════════════════════════════════════════════════════

async def _handle_reply_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    photo,
) -> None:
    question_id = user_data.get(user_id, {}).get("question_id")
    question = await db.get_question(question_id) if question_id else None
    if not question:
        await update.message.reply_text("❌ This question is no longer available.")
        user_state.pop(user_id, None)
        user_data.pop(user_id, None)
        return

    is_reply = bool(user_data.get(user_id, {}).get("parent_reply_id"))
    item_name = "reply" if is_reply else "answer"

    cleaned_text = sanitize_text_content(text, max_length=3000)
    if not cleaned_text:
        await update.message.reply_text(f"❗ Please write your {item_name} text.")
        return
    if not REPLY_RATE_LIMITER.allow(str(user_id), "reply"):
        await update.message.reply_text("⏳ You are sending messages too quickly. Please wait a moment.")
        return

    user_data.setdefault(user_id, {})
    user_data[user_id]["reply_text"] = cleaned_text
    if photo:
        user_data[user_id]["image_file_id"] = photo.file_id

    await _send_reply_preview(update, context, user_id)


async def _send_reply_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> None:
    data = user_data.get(user_id, {})
    text = data.get("reply_text", "")
    is_reply = bool(data.get("parent_reply_id"))
    heading = "reply" if is_reply else "answer"

    preview = f"<b>Preview your {heading}:</b>\n\n{text}"
    await update.message.reply_text(
        preview,
        parse_mode="HTML",
        reply_markup=kb_confirm_reply(is_reply=is_reply),
    )


async def post_reply(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> None:
    """Save reply to DB, send to user chat, notify question author. Called after confirm."""
    data = user_data.get(user_id, {})
    question_id = data.get("question_id")
    parent_reply_id = data.get("parent_reply_id")
    text = sanitize_text_content(data.get("reply_text", ""), max_length=3000)
    image_file_id = data.get("image_file_id")

    if not question_id or not text:
        return

    question = await db.get_question(question_id)
    if not question:
        await context.bot.send_message(chat_id=chat_id, text="❌ This question is no longer available.")
        user_state.pop(user_id, None)
        user_data.pop(user_id, None)
        return

    reply = await db.create_reply(question_id, user_id, text, parent_reply_id, image_file_id)
    log_event("reply_submitted", user_id, {"question_id": str(question_id), "reply_id": str(reply.get("_id", ""))})
    author = await db.get_user(user_id)
    reply_id = oid(reply)

    # Determine reply_to_message_id for Telegram threading
    reply_to_msg_id = None
    if parent_reply_id:
        parent = await db.get_reply(parent_reply_id)
        if parent:
            reply_to_msg_id = parent.get("telegram_message_id")

    try:
        msg_id = await send_reply_message(
            context, chat_id, reply, author or {}, question_id,
            viewer_id=user_id, reply_to_message_id=reply_to_msg_id,
        )
        # Persist the Telegram message ID on the reply
        await db.update_reply(reply_id, telegram_message_id=msg_id, telegram_chat_id=chat_id)
    except Exception as exc:
        logger.error("Error sending reply message: %s", exc)

    # Notify question author
    if question:
        sender = author or {}
        await notifications.notify_new_reply(context, question, reply, sender)

        # Update channel post keyboard to reflect the current reply count
        try:
            from utils import kb_channel_question
            new_count = question.get("reply_count", 0)
            if question.get("channel_chat_id") and question.get("channel_message_id"):
                await context.bot.edit_message_reply_markup(
                    chat_id=question["channel_chat_id"],
                    message_id=question["channel_message_id"],
                    reply_markup=kb_channel_question(question_id, new_count),
                )
        except Exception:
            pass  # Non-critical

    # Cleanup
    user_state.pop(user_id, None)
    user_data.pop(user_id, None)


# ═════════════════════════════════════════════════════════════════════════════
# SEARCH
# ═════════════════════════════════════════════════════════════════════════════

async def _handle_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    query: str,
) -> None:
    if not query:
        await update.message.reply_text("❗ Please enter a search term.")
        return

    questions, total = await db.search_questions(query, page=0)
    user_state[user_id] = IDLE

    if not questions:
        await update.message.reply_text(
            f"🔍 No results for <b>{query}</b>.",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    import urllib.parse
    q_enc = urllib.parse.quote(query)
    has_next = total > len(questions)
    kb = kb_search_nav(q_enc, page=0, has_next=has_next)

    lines = [f"🔍 <b>Results for:</b> {query} ({total} found)\n"]
    for i, q in enumerate(questions, 1):
        preview = q["text"][:80].replace("\n", " ")
        qid = oid(q)
        from config import BOT_USERNAME
        url = f"https://t.me/{BOT_USERNAME}?start=show_{qid}"
        lines.append(f"{i}. <a href='{url}'>{preview}…</a>")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _is_muted(user: dict) -> bool:
    from datetime import timezone
    from datetime import datetime
    if not user.get("is_muted"):
        return False
    muted_until = user.get("muted_until")
    if muted_until is None:
        return True
    if muted_until.tzinfo is None:
        muted_until = muted_until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < muted_until
