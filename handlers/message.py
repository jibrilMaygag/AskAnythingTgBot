from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_state, user_data,questions
from utils import build_question_keyboard


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    text = update.message.text

    if user_id in user_state:

        # user writing question
        if user_state[user_id] == "WRITING":

            # save question
            user_data[user_id]["question"] = text

            keyboard = [
                [InlineKeyboardButton("✅ Confirm", callback_data="confirm")]
            ]

            await update.message.reply_text(
                f"📌 Your Question:\n\n{text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        if user_state[user_id] == "WRITING_REPLY":

            question_id = user_data[user_id]["question_id"]

            questions[question_id]["replies"].append({
                "id": str(len(questions[question_id]["replies"]) + 1),
                "user": "Anonymous",
                "text": text,
                "upvotes": 0,
                "downvotes": 0,
                "voters": {
                    "up": set(),
                    "down": set()
                },
                "time": "now"
            })

            q = questions[question_id]

            await context.bot.edit_message_reply_markup(
                chat_id=q["chat_id"],
                message_id=q["message_id"],
                reply_markup=build_question_keyboard(question_id)
            )
            await update.message.reply_text("✅ Answer posted!")

            del user_state[user_id]
            del user_data[user_id]
            return
    else:
        await update.message.reply_text("Use /start to begin.")