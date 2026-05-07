import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from states import user_state, user_data,questions
from config import CHANNEL_USERNAME,BOT_USERNAME
from utils import build_question_keyboard


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # ---------------- ASK FLOW ----------------
    if data == "ask":

        user_state[user_id] = "SELECT_TOPIC"

        keyboard = [
            [InlineKeyboardButton("🎓 Education", callback_data="topic_edu")],
            [InlineKeyboardButton("💻 Tech", callback_data="topic_tech")],
            [InlineKeyboardButton("❤️ Life", callback_data="topic_life")],
            [InlineKeyboardButton("🌍 General", callback_data="topic_general")]
        ]

        await query.edit_message_text(
            "📌 Choose a topic:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ---------------- TOPIC SELECT ----------------
    elif data.startswith("topic_"):

        topic = data.split("_")[1]

        user_state[user_id] = "WRITING"
        user_data[user_id] = {"topic": topic}

        await query.edit_message_text(
            f"✍️ Topic: {topic}\n\nNow send your question:"
        )
    
    # ---------------- PAGINATION ----------------
    elif data.startswith("page:"):

        parts = data.split(":")
        question_id = parts[1]
        page = int(parts[2])

        q = questions.get(question_id)

        if not q:
            await query.answer("Not found")
            return

        replies = q["replies"]

        per_page = 10
        start_idx = page * per_page
        end_idx = start_idx + per_page

        shown = replies[start_idx:end_idx]

        for r in shown:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"👍 {r['upvotes']}", callback_data=f"up:{question_id}:{r['id']}"),
                    InlineKeyboardButton(f"👎 {r['downvotes']}", callback_data=f"down:{question_id}:{r['id']}")
                ]
            ])

            await query.message.reply_text(
                f"💬 {r['text']}\n\nBy: {r['user']}",
                reply_markup=keyboard
            )

        await query.answer("Page loaded")


# ---------------- CONFIRM ----------------
    elif data == "confirm":

        question = user_data[user_id]["question"]
        topic = user_data[user_id]["topic"]

        # CREATE UNIQUE ID
        question_id = uuid.uuid4().hex[:8]

        # ---------------- SAVE QUESTION FIRST ----------------
        questions[question_id] = {
            "topic": topic,
            "question": question,
            "user": update.effective_user.first_name,
            "replies": [],

            # temporary placeholders
            "message_id": None,
            "chat_id": None
        }

        # ---------------- POST TO CHANNEL ----------------
        msg = await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=(
                f"#{topic}\n\n"
                f"{question}\n\n"
                f"By: Anonymous 👩"
            ),
            reply_markup=build_question_keyboard(question_id)
        )

        # ---------------- SAVE REAL MESSAGE IDS ----------------
        questions[question_id]["message_id"] = msg.message_id
        questions[question_id]["chat_id"] = msg.chat_id

        # ---------------- CONFIRM TO USER ----------------
        await query.edit_message_text(
            "✅ Your question has been posted!"
        )

        # ---------------- CLEAR STATE ----------------
        del user_state[user_id]
        del user_data[user_id]
# ---------------- REPLY ----------------
    elif data.startswith("reply_"):

        question_id = data.split("_")[1]

        user_state[user_id] = "WRITING_REPLY"
        user_data[user_id] = {"question_id": question_id}

        await query.edit_message_text("✍️ Send your answer:")   
# ---------------- UPVOTE ----------------
    elif data.startswith("up:"):

        _, question_id, reply_id = data.split(":")

        user_id = query.from_user.id

        q = questions.get(question_id)

        if not q:
            return

        for r in q["replies"]:

            if r["id"] == reply_id:

                # already voted
                if user_id in r["voters"]["up"]:
                    return

                # remove downvote if exists
                if user_id in r["voters"]["down"]:
                    r["voters"]["down"].remove(user_id)
                    r["downvotes"] -= 1

                # add upvote
                r["voters"]["up"].add(user_id)
                r["upvotes"] += 1

                # 🔥 REALTIME BUTTON UPDATE
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            f"👍 {r['upvotes']}",
                            callback_data=f"up:{question_id}:{reply_id}"
                        ),
                        InlineKeyboardButton(
                            f"👎 {r['downvotes']}",
                            callback_data=f"down:{question_id}:{reply_id}"
                        )
                    ]
                ])

                await query.edit_message_reply_markup(
                    reply_markup=keyboard
                )
                return
# ---------------- DOWNVOTE ----------------
    elif data.startswith("down:"):

        _, question_id, reply_id = data.split(":")

        user_id = query.from_user.id

        q = questions.get(question_id)

        if not q:
            return

        for r in q["replies"]:

            if r["id"] == reply_id:

                if user_id in r["voters"]["down"]:
                    return

                if user_id in r["voters"]["up"]:
                    r["voters"]["up"].remove(user_id)
                    r["upvotes"] -= 1

                r["voters"]["down"].add(user_id)
                r["downvotes"] += 1

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            f"👍 {r['upvotes']}",
                            callback_data=f"up:{question_id}:{reply_id}"
                        ),
                        InlineKeyboardButton(
                            f"👎 {r['downvotes']}",
                            callback_data=f"down:{question_id}:{reply_id}"
                        )
                    ]
                ])

                await query.edit_message_reply_markup(
                    reply_markup=keyboard
                )

                return
# ---------------- REPORT ----------------
    elif data.startswith("report:"):

        reply_id = data.split(":")[1]

        for q in questions.values():
            for r in q["replies"]:
                if r["id"] == reply_id:
                    r["reports"] += 1
                    break


        await query.answer("🚫 Reported!")

# ---------------- REPLY TO REPLY ----------------
    elif data.startswith("reply:"):

        parts = data.split(":")
        question_id = parts[1]
        reply_id = parts[2]

        user_state[user_id] = "WRITING_REPLY_TO_REPLY"
        user_data[user_id] = {
            "question_id": question_id,
            "reply_id": reply_id
        }

        await query.edit_message_text("✍️ Write your reply:")
    elif data == "search":
        await query.edit_message_text("🔍 Type what you want to search:")

    elif data == "trending":
        await query.edit_message_text("🔥 Trending questions loading...")

    elif data == "leaderboard":
        await query.edit_message_text("📊 Top users will appear here")

    elif data == "profile":
        await query.edit_message_text("👤 Your profile info")

    elif data == "help":
        await query.edit_message_text("ℹ️ Use buttons to navigate the bot")