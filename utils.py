from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_USERNAME
from states import questions


def build_question_keyboard(question_id):

    q = questions[question_id]

    reply_count = len(q["replies"])

    answer_text = (
        f"💬 Show Answers ({reply_count})"
        if reply_count > 0
        else "💬 Show Answers"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "✍️ Answer",
                url=f"https://t.me/{BOT_USERNAME}?start=reply_{question_id}"
            ),
            InlineKeyboardButton(
                answer_text,
                url=f"https://t.me/{BOT_USERNAME}?start=show_{question_id}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)