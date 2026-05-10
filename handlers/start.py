"""
start.py – /start command handler.

Responsibilities:
  • Create user profile on first interaction (default: Anonymous, no forced setup)
  • Handle deep links:
      start=answer_<question_id>   → jump straight to reply flow
      start=show_<question_id>     → open question with paginated replies
  • Show main menu
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from states import user_state, user_data, IDLE, WRITING_REPLY, VIEWING_QUESTION
from utils import (
    kb_main_menu, kb_show_more,
    format_user_short,
    send_question_message, send_replies_batch,
    oid,
)
from config import REPLIES_PER_PAGE

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    user_id = tg_user.id
    chat_id = update.effective_chat.id

    # Ensure user exists (default profile, no forced setup)
    user = await db.get_or_create_user(
        telegram_id=user_id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )

    # Check ban
    if user.get("is_banned"):
        await update.message.reply_text("🚫 You are banned from this community.")
        return

    # ── Deep links ─────────────────────────────────────────────────────────
    if context.args:
        payload = context.args[0]

        if payload.startswith("answer_"):
            question_id = payload[7:]
            question = await db.get_question(question_id)
            if not question:
                await update.message.reply_text("❌ Question not found.")
                return
            user_state[user_id] = WRITING_REPLY
            user_data[user_id] = {"question_id": question_id, "parent_reply_id": None}
            await update.message.reply_text(
                "✍️ Write your answer:"
            )
            return

        if payload.startswith("show_"):
            question_id = payload[5:]
            await _show_question(update, context, user_id, chat_id, question_id)
            return

    # ── Main menu ──────────────────────────────────────────────────────────
    name = format_user_short(user)
    user_state[user_id] = IDLE
    await update.message.reply_text(
        f"👋 Welcome back, <b>{name}</b>!\n\nWhat would you like to do?",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )


async def _show_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    question_id: str,
) -> None:
    question = await db.get_question(question_id)
    if not question:
        await update.message.reply_text("❌ Question not found.")
        return

    author = await db.get_user(question["author_id"])

    # Send question card
    await send_question_message(context, chat_id, question, author or {})

    # Update state
    user_state[user_id] = VIEWING_QUESTION
    user_data[user_id] = {"question_id": question_id}

    # Send first page of replies
    sent, total = await send_replies_batch(
        context, chat_id, question_id,
        offset=0, limit=REPLIES_PER_PAGE, viewer_id=user_id,
    )

    if total == 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text="💬 No replies yet. Be the first to answer!",
        )
        return

    if sent < total:
        kb = kb_show_more(question_id, sent, total)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📄 Showing {sent} of {total} replies",
            reply_markup=kb,
        )
