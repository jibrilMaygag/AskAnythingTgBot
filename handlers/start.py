from telegram import Update
from telegram.ext import ContextTypes
from states import user_state, user_data, IDLE, SETTING_PROFILE, VIEWING_QUESTION
from utils import build_main_menu, send_question, send_replies_batch, build_show_more_keyboard
from database import get_user, create_user, get_question, set_view_offset


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command and deep links."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Ensure user exists in database
    if not get_user(user_id):
        create_user(user_id, update.effective_user.username)
    
    # ============= DEEP LINKS =============
    if context.args:
        payload = context.args[0]
        
        # Format: answer_QUESTION_ID (direct answer to question)
        if payload.startswith("answer_"):
            question_id = payload.replace("answer_", "")
            
            question = get_question(question_id)
            if not question:
                await update.message.reply_text("❌ Question not found")
                return
            
            user_state[user_id] = "WRITING_REPLY"
            user_data[user_id] = {
                "question_id": question_id,
                "parent_reply_id": None,
            }
            await update.message.reply_text("✍️ Write your answer:")
            return
        
        # Format: reply_REPLY_ID:QUESTION_ID
        if payload.startswith("reply_"):
            parts = payload.replace("reply_", "").split(":")
            reply_id = parts[0] if len(parts) > 0 else None
            question_id = parts[1] if len(parts) > 1 else None
            
            if reply_id and question_id:
                user_state[user_id] = "WRITING_REPLY_TO_REPLY"
                user_data[user_id] = {
                    "question_id": question_id,
                    "parent_reply_id": reply_id,
                }
                await update.message.reply_text("✍️ Write your reply:")
                return
        
        # Format: show_QUESTION_ID
        elif payload.startswith("show_"):
            question_id = payload.replace("show_", "")
            await _show_question(update, context, question_id)
            return
    
    # ============= PROFILE CHECK =============
    user = get_user(user_id)
    if not user.get("display_name"):
        user_state[user_id] = SETTING_PROFILE
        await update.message.reply_text(
            "👋 Welcome! Let's set up your profile first.\n\n"
            "What's your display name?"
        )
        return
    
    # ============= MAIN MENU =============
    user_state[user_id] = IDLE
    await update.message.reply_text(
        f"💬 Welcome back, {user['display_name']}!",
        reply_markup=build_main_menu()
    )


async def _show_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: str):
    """Show a question and its replies."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    question = get_question(question_id)
    if not question:
        await update.message.reply_text("❌ Question not found")
        return
    
    # Send question
    await send_question(context, chat_id, question_id, user_id)
    
    # Track viewing state
    user_state[user_id] = VIEWING_QUESTION
    user_data[user_id] = {
        "question_id": question_id,
        "viewed_replies": 0,
    }
    
    # Send first batch of replies
    messages_sent, total = await send_replies_batch(
        context,
        chat_id,
        question_id,
        count=10,
        offset=0,
        user_id=user_id
    )
    
    # Update offset
    set_view_offset(user_id, question_id, messages_sent)
    
    # Show "Show More" button if applicable
    if messages_sent < total:
        show_more_kb = build_show_more_keyboard(question_id, messages_sent, total)
        if show_more_kb:
            await update.message.reply_text(
                f"📄 Showing {messages_sent}/{total} replies",
                reply_markup=show_more_kb
            )
