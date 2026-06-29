"""
notifications.py – Notification delivery and formatting.

Currently handles:
  • New reply on a question  → notify question author
  • (Extensible for upvote, badge, moderation alerts, etc.)
"""

import logging
from typing import Optional

from telegram.ext import ContextTypes

import database as db
from config import BOT_USERNAME
from utils import format_user_short, oid

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# FORMATTERS
# ═════════════════════════════════════════════════════════════════════════════

def _build_new_reply_payload(
    question: dict,
    reply: dict,
    sender: dict,
) -> dict:
    """Build the notification payload stored in DB."""
    return {
        "type": "new_reply",
        "question_id": str(question["_id"]),
        "reply_id": str(reply["_id"]),
        "sender_id": reply["author_id"],
        "sender_display": format_user_short(sender),
        "sender_rep": sender.get("reputation", 0),
        "reply_preview": reply["text"][:120],
    }


def _format_new_reply_message(payload: dict) -> str:
    sender = payload["sender_display"]
    rep = payload["sender_rep"]
    preview = payload["reply_preview"]
    question_id = payload.get("question_id")
    reply_id = payload.get("reply_id")
    deep_link = f"https://t.me/{BOT_USERNAME}?start=show_{question_id}_{reply_id}"

    return (
        f"🎉 <b>You've got a new answer!</b>\n\n"
        f"{sender} just responded to your question.\n\n"
        f"<i>Tap to open the question and jump to the reply.</i>\n\n"
        f"──────────────\n"
        f'💬 "{preview}"\n\n'
        f"By: {sender} 🎖 {rep} rep\n\n"
        f"<a href=\"{deep_link}\">Open this reply</a>"
    )


# ═════════════════════════════════════════════════════════════════════════════
# DELIVERY
# ═════════════════════════════════════════════════════════════════════════════

async def notify_new_reply(
    context: ContextTypes.DEFAULT_TYPE,
    question: dict,
    reply: dict,
    sender: dict,
) -> None:
    """
    Notify the question author that a new reply has arrived.
    Skips if author == sender (own answer).
    """
    author_id: int = question.get("author_id")
    sender_id: int = reply.get("author_id")

    if not author_id or author_id == sender_id:
        return

    payload = _build_new_reply_payload(question, reply, sender)
    text = _format_new_reply_message(payload)

    # Persist to DB
    await db.create_notification(author_id, payload)

    # Attempt Telegram delivery (may fail if user blocked the bot)
    try:
        await context.bot.send_message(
            chat_id=author_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
    except Exception as exc:
        logger.info("Could not deliver notification to %s: %s", author_id, exc)


async def notify_question_approved(
    context: ContextTypes.DEFAULT_TYPE,
    question: dict,
    author: dict,
) -> None:
    author_id = question.get("author_id")
    if not author_id:
        return
    payload = {
        "type": "question_approved",
        "question_id": str(question["_id"]),
        "topic": question.get("topic", "general"),
    }
    await db.create_notification(author_id, payload)
    text = (
        f"✅ <b>Your question was approved</b>\n\n"
        f"It is now live in the community."
    )
    try:
        await context.bot.send_message(chat_id=author_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.info("Could not deliver approval notification to %s: %s", author_id, exc)


async def notify_question_rejected(
    context: ContextTypes.DEFAULT_TYPE,
    question: dict,
    author: dict,
    reason: str = None,
) -> None:
    author_id = question.get("author_id")
    if not author_id:
        return
    payload = {
        "type": "question_rejected",
        "question_id": str(question["_id"]),
        "reason": reason,
    }
    await db.create_notification(author_id, payload)
    text = "❌ <b>Your question was rejected</b>"
    if reason:
        text += f"\nReason: {reason}"
    try:
        await context.bot.send_message(chat_id=author_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.info("Could not deliver rejection notification to %s: %s", author_id, exc)


async def notify_reputation_change(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    delta: int,
    reason: str,
) -> None:
    """Optional: notify user of a reputation change."""
    direction = "gained" if delta > 0 else "lost"
    text = f"🎖 You {direction} <b>{abs(delta)}</b> reputation — {reason}"
    payload = {"type": "reputation", "delta": delta, "reason": reason}
    await db.create_notification(user_id, payload)
    try:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.info("Could not deliver rep notification to %s: %s", user_id, exc)
