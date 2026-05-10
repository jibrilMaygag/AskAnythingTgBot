"""
admin.py – Admin moderation commands and callback handlers.

Commands (admin-only):
  /admin            – show admin panel
  /stats            – engagement snapshot
  /reports          – list pending reports
  /ban <user_id>    – ban a user
  /unban <user_id>  – unban a user
  /mute <user_id>   – mute a user
  /unmute <user_id> – unmute a user

Callbacks:
  admin_delete:reply:<reply_id>:<report_id>
  admin_delete:question:<question_id>:<report_id>
  admin_dismiss:<report_id>
  admin_mute_from_report:<target_id>:<report_id>
"""

import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
from config import ADMIN_IDS
from analytics import get_dashboard_text
from utils import oid

logger = logging.getLogger(__name__)


# ── Guard decorator ───────────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.effective_message.reply_text("⛔ Admin only.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ═════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

@admin_only
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🚩 Pending Reports", callback_data="admin_reports")],
    ])
    await update.message.reply_text("🛡 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=keyboard)


@admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await get_dashboard_text()
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reports = await db.get_pending_reports(limit=10)
    if not reports:
        await update.message.reply_text("✅ No pending reports.")
        return
    for report in reports:
        await _send_report_card(context, update.effective_chat.id, report)


@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    target_id = int(context.args[0])
    await db.update_user(target_id, is_banned=True)
    await update.message.reply_text(f"🚫 User {target_id} banned.")


@admin_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    target_id = int(context.args[0])
    await db.update_user(target_id, is_banned=False)
    await update.message.reply_text(f"✅ User {target_id} unbanned.")


@admin_only
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute user for 24 hours. /mute <user_id> [hours]"""
    if not context.args:
        await update.message.reply_text("Usage: /mute <user_id> [hours]")
        return
    target_id = int(context.args[0])
    hours = int(context.args[1]) if len(context.args) > 1 else 24
    muted_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    await db.update_user(target_id, is_muted=True, muted_until=muted_until)
    await update.message.reply_text(f"🔇 User {target_id} muted for {hours}h.")


@admin_only
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unmute <user_id>")
        return
    target_id = int(context.args[0])
    await db.update_user(target_id, is_muted=False, muted_until=None)
    await update.message.reply_text(f"✅ User {target_id} unmuted.")


# ═════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

async def callback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("⛔ Admin only.", show_alert=True)
        return

    data = query.data

    if data == "admin_stats":
        text = await get_dashboard_text()
        await query.edit_message_text(text, parse_mode="HTML")

    elif data == "admin_reports":
        reports = await db.get_pending_reports(limit=10)
        if not reports:
            await query.edit_message_text("✅ No pending reports.")
            return
        await query.edit_message_text(f"🚩 {len(reports)} pending report(s):")
        for report in reports:
            await _send_report_card(context, query.message.chat_id, report)

    elif data.startswith("admin_delete:"):
        parts = data.split(":")
        target_type = parts[1]
        target_id = parts[2]
        report_id = parts[3]
        if target_type == "reply":
            await db.soft_delete_reply(target_id)
        else:
            await db.soft_delete_question(target_id)
        await db.resolve_report(report_id, user_id, "deleted")
        await query.edit_message_text("🗑 Content deleted and report resolved.")

    elif data.startswith("admin_dismiss:"):
        report_id = data.split(":")[1]
        await db.resolve_report(report_id, user_id, "dismissed")
        await query.edit_message_text("✅ Report dismissed.")

    elif data.startswith("admin_mute_from_report:"):
        parts = data.split(":")
        target_obj_id = parts[1]
        report_id = parts[2]
        # Lookup author from target
        reply = await db.get_reply(target_obj_id)
        if reply:
            muted_until = datetime.now(timezone.utc) + timedelta(hours=24)
            await db.update_user(reply["author_id"], is_muted=True, muted_until=muted_until)
            await db.resolve_report(report_id, user_id, "muted_author")
            await query.edit_message_text("🔇 Author muted 24h and report resolved.")
        else:
            await query.answer("Could not find target.", show_alert=True)


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _send_report_card(context: ContextTypes.DEFAULT_TYPE, chat_id: int, report: dict):
    from utils import kb_admin_report
    target_type = report.get("target_type", "reply")
    target_id = str(report["target_id"])
    report_id = str(report["_id"])
    reason = report.get("reason", "flagged")

    # Fetch preview
    preview = ""
    if target_type == "reply":
        target = await db.get_reply(target_id)
    else:
        target = await db.get_question(target_id)
    if target:
        preview = target.get("text", "")[:100]

    text = (
        f"🚩 <b>Report</b>\n"
        f"Type: {target_type}\n"
        f"Reason: {reason}\n"
        f"Preview: <i>{preview}</i>"
    )
    keyboard = kb_admin_report(report_id, target_type, target_id)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)


# ═════════════════════════════════════════════════════════════════════════════
# HANDLER REGISTRATION (called by main.py)
# ═════════════════════════════════════════════════════════════════════════════

def register(app) -> None:
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("reports", cmd_reports))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(
        CallbackQueryHandler(
            callback_admin,
            pattern=r"^(admin_stats|admin_reports|admin_delete:|admin_dismiss:|admin_mute_from_report:)",
        )
    )
