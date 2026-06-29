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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db
import notifications
from config import ADMIN_IDS, CHANNEL_USERNAME
from analytics import get_dashboard_text
from utils import oid

logger = logging.getLogger(__name__)


def parse_user_id_arg(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.effective_message.reply_text("⛔ Admin only.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def build_channel_post_url(channel_username: str, message_id: int | None) -> str | None:
    if not channel_username or message_id is None:
        return None
    username = channel_username.lstrip("@")
    return f"https://t.me/{username}/{message_id}" if username else None


# ═════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

def _admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ Pending Questions", callback_data="admin_pending_questions")],
        [InlineKeyboardButton("🚩 Reports", callback_data="admin_reports")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
    ])


@admin_only
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=_admin_panel_keyboard())


@admin_only
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await get_dashboard_text()
    await update.message.reply_text(text, parse_mode="HTML")


@admin_only
async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_reports(update, context, page=0)


@admin_only
async def cmd_pending_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_pending_questions(update, context, page=0)


@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    target_id = parse_user_id_arg(context.args[0])
    if target_id is None:
        await update.message.reply_text("❗ Please provide a valid Telegram user ID.")
        return
    await db.update_user(target_id, is_banned=True)
    await db.log_admin_action("user_banned", target_id, {"admin_id": update.effective_user.id})
    await update.message.reply_text(f"🚫 User {target_id} banned.")


@admin_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    target_id = parse_user_id_arg(context.args[0])
    if target_id is None:
        await update.message.reply_text("❗ Please provide a valid Telegram user ID.")
        return
    await db.update_user(target_id, is_banned=False)
    await db.log_admin_action("user_unbanned", target_id, {"admin_id": update.effective_user.id})
    await update.message.reply_text(f"✅ User {target_id} unbanned.")


@admin_only
async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mute user for 24 hours. /mute <user_id> [hours]"""
    if not context.args:
        await update.message.reply_text("Usage: /mute <user_id> [hours]")
        return
    target_id = parse_user_id_arg(context.args[0])
    if target_id is None:
        await update.message.reply_text("❗ Please provide a valid Telegram user ID.")
        return
    hours = int(context.args[1]) if len(context.args) > 1 else 24
    muted_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    await db.update_user(target_id, is_muted=True, muted_until=muted_until)
    await db.log_admin_action("user_muted", target_id, {"admin_id": update.effective_user.id, "hours": hours})
    await update.message.reply_text(f"🔇 User {target_id} muted for {hours}h.")


@admin_only
async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unmute <user_id>")
        return
    target_id = parse_user_id_arg(context.args[0])
    if target_id is None:
        await update.message.reply_text("❗ Please provide a valid Telegram user ID.")
        return
    await db.update_user(target_id, is_muted=False, muted_until=None)
    await db.log_admin_action("user_unmuted", target_id, {"admin_id": update.effective_user.id})
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

    if data == "admin_back":
        await query.edit_message_text("🛡 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=_admin_panel_keyboard())

    elif data == "admin_stats":
        text = await get_dashboard_text()
        await query.edit_message_text(text, parse_mode="HTML")

    elif data == "admin_reports":
        await _show_reports(query, context, page=0)

    elif data == "admin_pending_questions":
        await _show_pending_questions(query, context, page=0)

    elif data.startswith("ad:"):
        parts = data.split(":")
        target_type = "reply" if parts[1] == "r" else "question"
        report_id = parts[2]
        report = await db.get_pending_reports(limit=1)
        report_doc = None
        for candidate in report:
            if str(candidate.get("_id")) == report_id:
                report_doc = candidate
                break
        if not report_doc:
            report_doc = await db._db().reports.find_one({"_id": ObjectId(report_id)}) if hasattr(db, "_db") else None
        if report_doc:
            target_id = str(report_doc["target_id"])
            if target_type == "reply":
                await db.soft_delete_reply(target_id)
            else:
                await db.soft_delete_question(target_id)
            await db.resolve_report(report_id, user_id, "deleted")
            await db.log_admin_action("answer_deleted" if target_type == "reply" else "reply_deleted", user_id, {"target_id": target_id, "report_id": report_id})
            await query.edit_message_text("🗑 Content deleted and report resolved.")
        else:
            await query.edit_message_text("❌ Report not found.")

    elif data.startswith("di:"):
        report_id = data.split(":")[1]
        await db.resolve_report(report_id, user_id, "dismissed")
        await db.log_admin_action("report_ignored", user_id, {"report_id": report_id})
        await query.edit_message_text("✅ Report dismissed.")

    elif data.startswith("am:"):
        report_id = data.split(":")[1]
        report = await db._db().reports.find_one({"_id": ObjectId(report_id)}) if hasattr(db, "_db") else None
        if report:
            reply = await db.get_reply(report["target_id"])
            if reply:
                muted_until = datetime.now(timezone.utc) + timedelta(hours=24)
                await db.update_user(reply["author_id"], is_muted=True, muted_until=muted_until)
                await db.resolve_report(report_id, user_id, "muted_author")
                await db.log_admin_action("user_muted", user_id, {"target_id": reply["author_id"], "report_id": report_id, "hours": 24})
                await query.edit_message_text("🔇 Author muted 24h and report resolved.")
            else:
                await query.answer("Could not find target.", show_alert=True)
        else:
            await query.answer("Could not find target.", show_alert=True)


    elif data.startswith("admin_review:"):
        parts = data.split(":")
        action = parts[1]
        question_id = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        if action == "approve":
            question = await db.approve_question(question_id, user_id, "normal")
            if question:
                await db.log_admin_action("question_approved", user_id, {"question_id": question_id, "content_rating": "normal"})
                author = await db.get_user(question.get("author_id"))
                try:
                    from utils import send_question_message
                    msg = await send_question_message(context, CHANNEL_USERNAME, question, author or {}, is_channel_post=True)
                    post_url = build_channel_post_url(CHANNEL_USERNAME, msg.message_id)
                    await db.update_question(
                        question_id,
                        channel_chat_id=msg.chat.id,
                        channel_message_id=msg.message_id,
                        channel_post_url=post_url,
                    )
                    await notifications.notify_question_approved(context, question, author or {})
                    await query.edit_message_text("✅ Question approved and published.")
                except Exception as exc:
                    logger.exception("Failed to publish approved question: %s", exc)
                    await query.edit_message_text("⚠️ Question approved but publishing failed.")
            else:
                await query.edit_message_text("❌ Question not found.")
        elif action == "approve_sensitive":
            question = await db.approve_question(question_id, user_id, "sensitive")
            if question:
                await db.log_admin_action("question_approved", user_id, {"question_id": question_id, "content_rating": "sensitive"})
                author = await db.get_user(question.get("author_id"))
                try:
                    from utils import send_question_message
                    msg = await send_question_message(context, CHANNEL_USERNAME, question, author or {}, is_channel_post=True)
                    post_url = build_channel_post_url(CHANNEL_USERNAME, msg.message_id)
                    await db.update_question(
                        question_id,
                        channel_chat_id=msg.chat.id,
                        channel_message_id=msg.message_id,
                        channel_post_url=post_url,
                    )
                    await notifications.notify_question_approved(context, question, author or {})
                    await query.edit_message_text("✅ Sensitive question approved and published.")
                except Exception as exc:
                    logger.exception("Failed to publish sensitive question: %s", exc)
                    await query.edit_message_text("⚠️ Sensitive question approved but publishing failed.")
            else:
                await query.edit_message_text("❌ Question not found.")
        else:
            question = await db.reject_question(question_id, user_id, "Rejected by admin")
            if question:
                await db.log_admin_action("question_rejected", user_id, {"question_id": question_id})
                author = await db.get_user(question.get("author_id"))
                await notifications.notify_question_rejected(context, question, author or {}, "Rejected by admin")
                await query.edit_message_text("❌ Question rejected.")
            else:
                await query.edit_message_text("❌ Question not found.")
        await _show_pending_questions(query, context, page=page)

    elif data.startswith("admin_report_page:"):
        page = int(data.split(":")[2])
        await _show_reports(query, context, page=page)


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _show_pending_questions(update_or_query, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    questions = await db.get_pending_questions(skip=page * 1, limit=1)
    if not questions:
        text = "✅ No pending questions."
        if hasattr(update_or_query, "edit_message_text"):
            await update_or_query.edit_message_text(text)
        else:
            await update_or_query.message.reply_text(text)
        return

    question = questions[0]
    author = await db.get_user(question.get("author_id"))
    created_at = question.get("created_at")
    created_text = created_at.strftime("%Y-%m-%d %H:%M UTC") if created_at else "unknown"
    text = (
        f"⏳ <b>Pending Question</b>\n\n"
        f"Topic: <b>{question.get('topic', 'general')}</b>\n"
        f"Text: {question.get('text', '')}\n"
        f"Author: {question.get('author_id')}\n"
        f"Submitted: {created_text}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"admin_review:approve:{oid(question)}:{page}")],
        [InlineKeyboardButton("⚠️ Approve as Sensitive", callback_data=f"admin_review:approve_sensitive:{oid(question)}:{page}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"admin_review:reject:{oid(question)}:{page}")],
        [InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_pending_questions:{page-1}"), InlineKeyboardButton("Next ➡️", callback_data=f"admin_pending_questions:{page+1}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")],
    ])
    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await update_or_query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _show_reports(update_or_query, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    from utils import kb_admin_report
    reports = await db.get_pending_reports(limit=5, skip=page * 5)
    if not reports:
        text = "✅ No pending reports."
        if hasattr(update_or_query, "edit_message_text"):
            await update_or_query.edit_message_text(text)
        else:
            await update_or_query.message.reply_text(text)
        return

    lines = [f"🚩 <b>Pending Reports</b> ({len(reports)} shown)"]
    for report in reports:
        reason = report.get("reason", "flagged")
        target_type = report.get("target_type", "reply")
        target_id = str(report["target_id"])
        report_id = str(report["_id"])
        preview = ""
        if target_type == "reply":
            target = await db.get_reply(target_id)
        else:
            target = await db.get_question(target_id)
        if target:
            preview = target.get("text", "")[:80]
        lines.append(f"\n• {target_type}: {preview or 'no preview'}\nReason: {reason}")
        keyboard = kb_admin_report(report_id, target_type, target_id)
        if hasattr(update_or_query, "edit_message_text"):
            await context.bot.send_message(chat_id=update_or_query.message.chat_id, text="\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
            lines = []
        else:
            await context.bot.send_message(chat_id=update_or_query.effective_chat.id, text="\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
            lines = []

    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text("🚩 Reports loaded.")


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
    app.add_handler(CommandHandler("pending", cmd_pending_questions))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(
        CallbackQueryHandler(
            callback_admin,
            pattern=r"^(admin_|admin_review:|admin_report_page:|ad:|di:|am:)",
        )
    )
