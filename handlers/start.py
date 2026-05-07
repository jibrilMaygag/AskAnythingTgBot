from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from states import questions,user_state,user_data


def main_menu():
    keyboard = [
        [InlineKeyboardButton("✍️ Ask Question", callback_data="ask")],
        [InlineKeyboardButton("🔍 Search Questions", callback_data="search")],

        [InlineKeyboardButton("🔥 Trending", callback_data="trending")],
        [InlineKeyboardButton("⭐ Top Answers", callback_data="answers")],

        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("📊 Leaderboard", callback_data="leaderboard")],

        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📜 Rules", callback_data="rules")],
        [InlineKeyboardButton("🔗 Invite Friends", callback_data="invite")]
    ]

    return InlineKeyboardMarkup(keyboard)


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from states import questions


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    # ---------------- OPEN QUESTION ROUTES ----------------
    if context.args:

        payload = context.args[0]

        # ---------------- REPLY ----------------
        if payload.startswith("reply_"):

            question_id = payload.replace("reply_", "")

            q = questions.get(question_id)

            if not q:
                await update.message.reply_text("❌ Question not found.")
                return

            user_state[user_id] = "WRITING_REPLY"
            user_data[user_id] = {
                "question_id": question_id
            }

            await update.message.reply_text("✍️ Send your answer now:")
            return  # 🔥 IMPORTANT FIX

        # ---------------- SHOW QUESTION ----------------
        elif payload.startswith("show_"):

            question_id = payload.replace("show_", "")
            q = questions.get(question_id)

            if not q:
                await update.message.reply_text("❌ Question not found.")
                return

            replies = q["replies"]

            # ---------------- HEADER ----------------
            await update.message.reply_text(
                f"💬 #{q['topic']}\n\n{q['question']}\n\nBy: {q['user']}"
            )

            # ---------------- NO REPLIES ----------------
            if len(replies) == 0:
                await update.message.reply_text("❌ No answers yet.")
                return

            # ---------------- PAGINATION LOGIC ----------------
            page = 0
            per_page = 10

            start_idx = page * per_page
            end_idx = start_idx + per_page

            shown = replies[start_idx:end_idx]

            for r in shown:

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"👍 {r['upvotes']}", callback_data=f"up:{question_id}:{r['id']}"),
                        InlineKeyboardButton(f"👎 {r['downvotes']}", callback_data=f"down:{question_id}:{r['id']}")
                    ],
                    [
                        InlineKeyboardButton("🚫 Report", callback_data=f"report:{question_id}:{r['id']}"),
                        InlineKeyboardButton("↩️ Reply", callback_data=f"reply:{question_id}:{r['id']}")
                    ]
                ])

                await update.message.reply_text(
                    f"💬 {r['text']}\n\n"
                    f"By: {r['user']} 🎖 {r['upvotes']} rep\n"
                    f"{r['time']}",
                    reply_markup=keyboard
                )

            # ---------------- NAVIGATION ----------------
            nav = []

            if len(replies) > end_idx:
                nav.append(
                    InlineKeyboardButton(
                        "➡️ Show More",
                        callback_data=f"page:{question_id}:{page+1}"
                    )
                )

            nav.append(
                InlineKeyboardButton(
                    f"📄 Show All ({len(replies)})",
                    callback_data=f"all:{question_id}"
                )
            )

            await update.message.reply_text(
                f"Showing {len(shown)} out of {len(replies)} replies",
                reply_markup=InlineKeyboardMarkup([nav])
            )

            return
    # ---------------- NORMAL HOME ----------------
    await update.message.reply_text(
        "💬 Weydii Waxwalba",
        reply_markup=main_menu()
    )