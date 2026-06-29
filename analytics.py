"""
analytics.py – Engagement tracking and statistics helpers.

All heavy queries go through database.py.
This module owns formatting and scheduled snapshot logic.
"""

import logging
from datetime import datetime, timezone

from telegram.ext import ContextTypes

import database as db
from config import ADMIN_IDS

logger = logging.getLogger(__name__)


async def get_dashboard_text() -> str:
    """Return a formatted stats summary for admins."""
    stats = await db.get_stats_snapshot()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"📊 <b>Moderation Statistics</b>\n"
        f"<i>{now}</i>\n\n"
        f"👥 Total users:          <b>{stats['total_users']}</b>\n"
        f"🟢 Active today:         <b>{stats['active_users_today']}</b>\n"
        f"❓ Total questions:      <b>{stats['total_questions']}</b>\n"
        f"⏳ Pending questions:    <b>{stats['pending_questions']}</b>\n"
        f"✅ Approved questions:  <b>{stats['approved_questions']}</b>\n"
        f"💬 Answers / replies:   <b>{stats['total_answers']}</b>\n"
        f"🚩 Pending reports:      <b>{stats['pending_reports']}</b>\n"
        f"🚫 Banned users:         <b>{stats['banned_users']}</b>\n"
        f"🔇 Muted users:          <b>{stats['muted_users']}</b>\n"
        f"📅 Questions today:     <b>{stats['questions_today']}</b>\n"
        f"📅 Answers today:       <b>{stats['answers_today']}</b>\n"
    )


async def broadcast_daily_snapshot(context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB JobQueue callback – send daily stats to all admins."""
    text = await get_dashboard_text()
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception as exc:
            logger.warning("Could not send snapshot to admin %s: %s", admin_id, exc)
