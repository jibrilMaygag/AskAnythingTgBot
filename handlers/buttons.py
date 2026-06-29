"""
buttons.py – Handles ALL callback_query updates.

Routing map (callback_data prefix → handler):
  ask                     → start ask flow
  topic_*                 → topic selected
  add_question_image      → await image for question
  confirm_question        → post question to channel
  add_reply_image         → await image for reply
  confirm_reply           → post reply
  cancel                  → reset state, show menu
  main_menu               → show main menu
  profile                 → show profile card
  profile_set_name        → start name-change flow
  profile_set_gender      → show gender picker
  gender_*                → save gender
  vote_up:*               → upvote reply
  vote_down:*             → downvote reply
  report_reply:*          → report reply
  reply_to:*              → start reply-to-reply flow
  show_more:*             → next page of replies
  show_all:*              → all remaining replies
  trending:*              → trending page
  leaderboard:*           → leaderboard page
  search                  → prompt search input
  search_page:*           → paginate search results
  (admin_* handled in admin.py)
"""

import logging
import urllib.parse
from math import ceil

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import BOT_USERNAME, REPLIES_PER_PAGE, TRENDING_PER_PAGE, LEADERBOARD_PER_PAGE
from states import user_state, user_data, IDLE, CHOOSING_TOPIC, WRITING_QUESTION, WRITING_QUESTION_IMAGE, WRITING_REPLY, WRITING_REPLY_IMAGE, SETTING_NAME, SEARCHING
from utils import (
    kb_main_menu, kb_topic, kb_profile, kb_gender,
    kb_show_more, kb_trending_nav, kb_leaderboard_nav, kb_search_nav,
    format_profile_text, format_user_display,
    send_question_message, send_replies_batch,
    update_reply_vote_keyboard,
    oid,
)

logger = logging.getLogger(__name__)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    data = query.data

    user = await db.get_or_create_user(user_id)
    if user.get("is_banned"):
        await query.answer("🚫 You are banned.", show_alert=True)
        return

    # ── Navigation ──────────────────────────────────────────────────────────
    if data == "main_menu":
        user_state[user_id] = IDLE
        user_data.pop(user_id, None)
        await query.edit_message_text(
            "What would you like to do?", reply_markup=kb_main_menu()
        )
        return

    if data == "cancel":
        user_state[user_id] = IDLE
        user_data.pop(user_id, None)
        await query.edit_message_text(
            "❌ Cancelled.", reply_markup=kb_main_menu()
        )
        return

    # ── Ask question ────────────────────────────────────────────────────────
    if data == "ask":
        user_state[user_id] = CHOOSING_TOPIC
        await query.edit_message_text(
            "📌 Choose a topic:", reply_markup=kb_topic()
        )
        return

    if data.startswith("topic_"):
        topic = data[6:]
        user_state[user_id] = WRITING_QUESTION
        user_data[user_id] = {"topic": topic}
        # Compact preview: inline lowercase tag without bold for smaller appearance
        await query.edit_message_text(
            f"✍️ Topic: #{topic}\n\nSend your question text:",
        )
        return

    if data == "confirm_question":
        from handlers.message import post_question_to_channel
        await query.edit_message_text("⏳ Sending your question for review…")
        await post_question_to_channel(context, user_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ Your question has been submitted for review.",
            reply_markup=kb_main_menu(),
        )
        return

    # ── Reply ───────────────────────────────────────────────────────────────
    if data == "confirm_reply":
        from handlers.message import post_reply
        await query.edit_message_text("⏳ Posting your reply…")
        await post_reply(context, chat_id, user_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ Reply posted!",
            reply_markup=kb_main_menu(),
        )
        return

    if data.startswith("reply_to:"):
        parts = data.split(":")
        parent_reply_id = parts[1]
        question_id = parts[2]
        user_state[user_id] = WRITING_REPLY
        user_data[user_id] = {
            "question_id": question_id,
            "parent_reply_id": parent_reply_id,
        }
        # Keep the original reply message unchanged; send a separate prompt to the user
        await context.bot.send_message(chat_id=chat_id, text="✍️ Write your reply:")
        return

    # ── Profile ─────────────────────────────────────────────────────────────
    if data == "profile":
        user = await db.get_user(user_id)
        text = await format_profile_text(user or {})
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_profile())
        return

    if data == "profile_set_name":
        user_state[user_id] = SETTING_NAME
        await query.edit_message_text(
            "✏️ Send your new display name (max 32 chars):"
        )
        return

    if data == "profile_set_gender":
        await query.edit_message_text(
            "🚻 Choose your gender:", reply_markup=kb_gender(include_skip=False)
        )
        return

    # profile image functionality removed

    if data.startswith("gender_"):
        gender = data[7:]  # "M" | "F" | "skip"
        if gender != "skip":
            await db.update_user(user_id, gender=gender)
        user_state[user_id] = IDLE
        user = await db.get_user(user_id)
        profile_text = await format_profile_text(user or {})
        await query.edit_message_text(
            "✅ Gender updated!\n\n" + profile_text,
            parse_mode="HTML",
            reply_markup=kb_profile(),
        )
        return

    # ── Voting ──────────────────────────────────────────────────────────────
    if data.startswith("vote_up:") or data.startswith("vote_down:"):
        direction = "up" if data.startswith("vote_up:") else "down"
        parts = data.split(":")
        reply_id = parts[1]
        question_id = parts[2]
        changed, prev = await db.cast_vote(reply_id, "reply", user_id, direction)
        if not changed:
            await query.answer("Already voted!", show_alert=False)
            return
        label = "👍 Liked!" if direction == "up" else "👎 Disliked!"
        await query.answer(label, show_alert=False)
        await update_reply_vote_keyboard(
            context, chat_id, message_id, reply_id, question_id, viewer_id=user_id
        )
        return

    # ── Report ──────────────────────────────────────────────────────────────
    if data.startswith("report_reply:"):
        reply_id = data[13:]
        added = await db.add_report(reply_id, "reply", user_id)
        if added:
            await query.answer("🚩 Reply reported. Moderators will review it.", show_alert=True)
        else:
            await query.answer("Already reported.", show_alert=False)

        reply = await db.get_reply(reply_id)
        question_id = str(reply["question_id"]) if reply else ""
        await update_reply_vote_keyboard(
            context, chat_id, message_id, reply_id, question_id,
            viewer_id=user_id,
        )
        return

    # ── Pagination: replies ─────────────────────────────────────────────────
    if data.startswith("show_more:"):
        parts = data.split(":")
        question_id = parts[1]
        offset = int(parts[2])
        sent, total = await send_replies_batch(
            context, chat_id, question_id,
            offset=offset, limit=REPLIES_PER_PAGE, viewer_id=user_id,
        )
        new_offset = offset + sent
        if new_offset < total:
            kb = kb_show_more(question_id, new_offset, total)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📄 Showing {new_offset} of {total} replies",
                reply_markup=kb,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=f"✅ All {total} replies loaded."
            )
        return

    if data.startswith("show_all:"):
        parts = data.split(":")
        question_id = parts[1]
        offset = int(parts[2])
        # Fetch total first, then request everything remaining
        _, total = await db.get_replies_for_question(question_id, offset=0, limit=1)
        sent, total = await send_replies_batch(
            context, chat_id, question_id,
            offset=offset, limit=max(total - offset, 1), viewer_id=user_id,
        )
        await context.bot.send_message(
            chat_id=chat_id, text=f"✅ All {total} replies loaded."
        )
        return

    # ── Trending ────────────────────────────────────────────────────────────
    if data.startswith("trending:"):
        page = int(data.split(":")[1])
        await _show_trending(query, context, page)
        return

    # ── Leaderboard ─────────────────────────────────────────────────────────
    if data.startswith("leaderboard:"):
        page = int(data.split(":")[1])
        await _show_leaderboard(query, context, page)
        return

    # ── Search ──────────────────────────────────────────────────────────────
    if data == "search":
        user_state[user_id] = SEARCHING
        await query.edit_message_text(
            "🔍 Send your search query:"
        )
        return

    if data.startswith("search_page:"):
        parts = data.split(":")
        raw_query = urllib.parse.unquote(parts[1])
        page = int(parts[2])
        await _show_search_page(query, context, raw_query, page)
        return


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _show_trending(query, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    questions, total = await db.get_trending_questions(page=page)
    total_pages = max(1, ceil(total / TRENDING_PER_PAGE))

    if not questions:
        await query.edit_message_text("🔥 No trending questions yet.", reply_markup=kb_main_menu())
        return

    lines = [f"🔥 <b>Trending Questions</b> (page {page + 1}/{total_pages})\n"]
    for q in questions:
        preview = q["text"][:60].replace("\n", " ")
        reply_count = q.get("reply_count", 0)
        qid = oid(q)
        post_url = q.get("channel_post_url") or f"https://t.me/{BOT_USERNAME}?start=show_{qid}"
        lines.append(
            f"❓ <a href='{post_url}'>{preview}…</a>\n"
            f"   💬 {reply_count} replies\n"
        )

    kb = kb_trending_nav(page, total_pages)
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )


async def _show_leaderboard(query, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    users = await db.get_leaderboard(page=page)
    has_next = len(users) == LEADERBOARD_PER_PAGE

    if not users:
        await query.edit_message_text("🏆 No users yet.", reply_markup=kb_main_menu())
        return

    lines = [f"🏆 <b>Reputation Leaderboard</b> (page {page + 1})\n"]
    medals = ["🥇", "🥈", "🥉"]
    start_rank = page * LEADERBOARD_PER_PAGE + 1
    for i, u in enumerate(users):
        rank = start_rank + i
        medal = medals[rank - 1] if rank <= 3 else f"{rank}."
        display = format_user_display(u)
        lines.append(f"{medal} {display}")

    kb = kb_leaderboard_nav(page, has_next)
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _show_search_page(query, context: ContextTypes.DEFAULT_TYPE, raw_query: str, page: int) -> None:
    questions, total = await db.search_questions(raw_query, page=page)
    has_next = (page + 1) * 8 < total

    if not questions:
        await query.edit_message_text(
            f"🔍 No results for <b>{raw_query}</b>.",
            parse_mode="HTML",
            reply_markup=kb_main_menu(),
        )
        return

    q_enc = urllib.parse.quote(raw_query)
    kb = kb_search_nav(q_enc, page=page, has_next=has_next)

    lines = [f"🔍 <b>Results for:</b> {raw_query} ({total} found, page {page + 1})\n"]
    for i, q in enumerate(questions, page * 8 + 1):
        preview = q["text"][:80].replace("\n", " ")
        qid = oid(q)
        url = f"https://t.me/{BOT_USERNAME}?start=show_{qid}"
        lines.append(f"{i}. <a href='{url}'>{preview}…</a>")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )
