from telegram import Update
from telegram.ext import ContextTypes
from states import user_state, user_data, SETTING_PROFILE, SETTING_GENDER, WRITING_QUESTION, CONFIRMING_QUESTION, WRITING_REPLY
from utils import build_confirm_keyboard, build_profile_setup_keyboard, build_main_menu, send_reply
from database import (
    get_user, update_user, create_question, create_reply,
    get_question, set_user_profile
)
from config import CHANNEL_USERNAME


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all user text messages."""
    user_id = update.effective_user.id
    text = update.message.text
    chat_id = update.effective_chat.id
    
    # ============= PROFILE SETUP =============
    if user_state.get(user_id) == SETTING_PROFILE:
        user_data[user_id] = {"display_name": text}
        user_state[user_id] = SETTING_GENDER
        
        await update.message.reply_text(
            f"Nice to meet you, <b>{text}</b>! 👋\n\n"
            "Now choose your gender (optional):",
            reply_markup=build_profile_setup_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # ============= QUESTION WRITING =============
    if user_state.get(user_id) == WRITING_QUESTION:
        user_data[user_id]["question"] = text
        user_state[user_id] = CONFIRMING_QUESTION
        
        await update.message.reply_text(
            f"📌 <b>Your Question:</b>\n\n{text}\n\n"
            "Confirm or cancel?",
            reply_markup=build_confirm_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # ============= REPLY WRITING =============
    if user_state.get(user_id) == WRITING_REPLY:
        await _save_reply(update, context, text)
        return
    
    # ============= IDLE - NO CONTEXT =============
    await update.message.reply_text(
        "💬 Use /start to begin or click a button",
        reply_markup=build_main_menu()
    )


async def _save_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save question and post to channel."""
    user_id = update.effective_user.id
    
    data = user_data.get(user_id, {})
    topic = data.get("topic")
    question_text = data.get("question")
    
    if not topic or not question_text:
        await update.message.reply_text("❌ Error saving question")
        return
    
    # Create question in database
    question = create_question(user_id, topic, question_text)
    
    # Post to channel
    try:
        msg = await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=(
                f"<b>#{question['topic'].upper()}</b>\n\n"
                f"{question['text']}\n\n"
                f"<i>by {get_user(user_id)['display_name']}</i>"
            ),
            parse_mode="HTML"
        )
        
        # Update question with message IDs
        from database import update_question
        update_question(question['id'], message_id=msg.message_id, chat_id=msg.chat_id)
        
        await update.message.reply_text(
            "✅ Question posted!",
            reply_markup=build_main_menu()
        )
    except Exception as e:
        print(f"Error posting to channel: {e}")
        await update.message.reply_text("❌ Error posting to channel")
    
    # Cleanup
    user_state.pop(user_id, None)
    user_data.pop(user_id, None)


async def _save_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Save reply to database and send to chat."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    data = user_data.get(user_id, {})
    question_id = data.get("question_id")
    parent_reply_id = data.get("parent_reply_id")
    
    if not question_id:
        await update.message.reply_text("❌ Question not found")
        return
    
    # Create reply
    reply = create_reply(question_id, user_id, text, parent_reply_id)
    
    # For now, send reply to user's chat (not to channel)
    # In production, you might post to channel and store message_id
    try:
        await send_reply(
            context,
            chat_id,
            reply["id"],
            question_id,
            user_id
        )
        
        await update.message.reply_text("✅ Reply posted!")
        
        # Update channel message to show new answer count
        question = get_question(question_id)
        if question and question.get("message_id") and question.get("chat_id"):
            try:
                from utils import build_channel_question_keyboard
                keyboard = build_channel_question_keyboard(question_id)
                await context.bot.edit_message_reply_markup(
                    chat_id=question["chat_id"],
                    message_id=question["message_id"],
                    reply_markup=keyboard
                )
            except Exception as e:
                print(f"Error updating channel message: {e}")
    except Exception as e:
        print(f"Error posting reply: {e}")
        await update.message.reply_text("❌ Error posting reply")
    
    # Cleanup
    user_state.pop(user_id, None)
    user_data.pop(user_id, None)
