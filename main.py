"""
main.py – Application entry point.

Responsibilities:
  • Build the PTB Application
  • Register all handlers in correct priority order
  • Bootstrap MongoDB indexes
  • Schedule periodic analytics snapshots
  • Start polling
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import TOKEN
from database import create_indexes

# Handler modules
from handlers.start import start
from handlers.buttons import button_handler
from handlers.message import message_handler
import admin

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Misc commands ─────────────────────────────────────────────────────────────
async def cmd_help(update: Update, _) -> None:
    await update.message.reply_text(
        "💬 <b>AskAnything Bot</b>\n\n"
        "/start – Main menu\n"
        "/help  – This message\n\n"
        "Tap <b>Ask Question</b> to post your first question!",
        parse_mode="HTML",
    )


async def error_handler(update: object, context) -> None:
    logger.error("Unhandled exception", exc_info=context.error)


# ── Post-init: create DB indexes ──────────────────────────────────────────────
async def post_init(app: Application) -> None:
    await create_indexes()
    logger.info("MongoDB indexes ready.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Core commands ─────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))

    # ── Admin commands ────────────────────────────────────────────────────
    admin.register(app)

    # ── Callback queries (buttons) ────────────────────────────────────────
    # Admin callbacks handled separately (registered inside admin.register)
    # Non-admin callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    # ── Text & photo messages ─────────────────────────────────────────────
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
            message_handler,
        )
    )

    # ── Profile image upload (state = SETTING_IMAGE) ──────────────────────
    app.add_handler(
        MessageHandler(filters.PHOTO, _handle_profile_image)
    )

    # ── Error handler ─────────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    # ── Optional: daily analytics snapshot (every 24h) ────────────────────
    from analytics import broadcast_daily_snapshot
    app.job_queue.run_repeating(
        broadcast_daily_snapshot,
        interval=86400,
        first=10,
        name="daily_snapshot",
    )

    logger.info("Bot is starting…")
    app.run_polling(poll_interval=2, drop_pending_updates=True)


async def _handle_profile_image(update: Update, context) -> None:
    """Save profile image file_id for users in SETTING_IMAGE state."""
    from states import user_state, IDLE
    import database as db
    from utils import kb_profile, format_profile_text

    user_id = update.effective_user.id
    if user_state.get(user_id) != "SETTING_IMAGE":
        return  # Let message_handler deal with it normally

    photo = update.message.photo[-1]
    await db.update_user(user_id, profile_image=photo.file_id)
    user_state[user_id] = IDLE
    user = await db.get_user(user_id)

    await update.message.reply_text(
        "🖼 Profile photo updated!\n\n" + format_profile_text(user or {}),
        parse_mode="HTML",
        reply_markup=kb_profile(),
    )


if __name__ == "__main__":
    main()
