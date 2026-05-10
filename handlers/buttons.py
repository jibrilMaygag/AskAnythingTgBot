from telegram import Update
from telegram.ext import ContextTypes
from states import user_state, user_data, IDLE, CHOOSING_TOPIC, WRITING_QUESTION, WRITING_REPLY
from utils import (
    build_main_menu, build_topic_keyboard, build_show_more_keyboard,
    send_reply, update_reply_vote_display, send_replies_batch
)
from database import (
    get_question, get_reply, change_vote, add_vote, add_report,
    get_user_vote, get_view_offset, set_view_offset, create_question, 
    update_question, get_replies_for_question, get_user
)
from config import CHANNEL_USERNAME


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callback button presses."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    data = query.data
    
    # ============= MAIN MENU BUTTONS =============
    if data == "ask":
        user_state[user_id] = CHOOSING_TOPIC
        await query.edit_message_text(
            "📌 Choose a topic:",
            reply_markup=build_topic_keyboard()
        )
    
    # ============= TOPIC SELECTION =============
    elif data.startswith("topic_"):
        topic = data.split("_")[1]
        user_state[user_id] = WRITING_QUESTION
        user_data[user_id] = {"topic": topic}
        
        await query.edit_message_text(
            f"✍️ Topic: <b>#{topic}</b>\n\n"
            "Now send your question:",
            parse_mode="HTML"
        )
    
    # ============= CONFIRM QUESTION =============
    elif data == "confirm_question":
        await _confirm_question(query, context, user_id)
    
    # ============= PROFILE BUTTONS =============
    elif data.startswith("gender_"):
        gender = data.split("_")[1]
        if gender != "skip":
            user_data[user_id]["gender"] = gender
        
        # Save profile
        display_name = user_data[user_id].get("display_name")
        gender_value = user_data[user_id].get("gender") if gender != "skip" else None
        
        from database import set_user_profile
        set_user_profile(user_id, display_name, gender_value)
        
        user_state[user_id] = IDLE
        await query.edit_message_text(
            "✅ Profile setup complete!",
            reply_markup=build_main_menu(),
            parse_mode="HTML"
        )
    
    # ============= VOTING =============
    elif data.startswith("vote_up:") or data.startswith("vote_down:"):
        await _handle_vote(query, context, user_id, data)
    
    # ============= REPORTING =============
    elif data.startswith("report:"):
        reply_id = data.split(":")[1]
        success = add_report(reply_id, user_id)
        
        if success:
            await query.answer("🚩 Reply reported!", show_alert=True)
        else:
            await query.answer("Already reported", show_alert=False)
    
    # ============= REPLY TO REPLY =============
    elif data.startswith("reply_to_reply:"):
        reply_id = data.split(":")[1]
        question_id = data.split(":")[2]
        
        user_state[user_id] = WRITING_REPLY
        user_data[user_id] = {
            "question_id": question_id,
            "parent_reply_id": reply_id,
        }
        
        await query.edit_message_text("✍️ Write your reply:")
    
    # ============= SHOW MORE REPLIES =============
    elif data.startswith("show_more:"):
        parts = data.split(":")
        question_id = parts[1]
        current_offset = int(parts[2])
        
        new_offset = current_offset + 10
        messages_sent, total = await send_replies_batch(
            context,
            chat_id,
            question_id,
            count=10,
            offset=current_offset,
            user_id=user_id
        )
        
        set_view_offset(user_id, question_id, new_offset)
        
        if new_offset < total:
            show_more_kb = build_show_more_keyboard(question_id, new_offset, total)
            if show_more_kb:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📄 Showing {new_offset}/{total} replies",
                    reply_markup=show_more_kb
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📄 All {total} replies loaded"
            )
    
    # ============= SHOW ALL REPLIES =============
    elif data.startswith("show_all:"):
        parts = data.split(":")
        question_id = parts[1]
        current_offset = int(parts[2])
        
        all_replies = get_replies_for_question(question_id)
        total = len(all_replies)
        
        messages_sent, _ = await send_replies_batch(
            context,
            chat_id,
            question_id,
            count=total,
            offset=current_offset,
            user_id=user_id
        )
        
        set_view_offset(user_id, question_id, total)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Loaded all {total} replies"
        )
    
    # ============= PLACEHOLDER BUTTONS =============
    elif data == "search":
        await query.edit_message_text("🔍 Search feature coming soon...")
    elif data == "trending":
        await query.edit_message_text("🔥 Trending questions coming soon...")
    elif data == "profile":
        await query.edit_message_text("👤 Your profile coming soon...")
    elif data == "cancel_question":
        user_state[user_id] = IDLE
        await query.edit_message_text(
            "❌ Question cancelled",
            reply_markup=build_main_menu()
        )


async def _confirm_question(query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Confirm and save question."""
    data = user_data.get(user_id, {})
    topic = data.get("topic")
    question_text = data.get("question")
    
    if not topic or not question_text:
        await query.answer("❌ Error saving question", show_alert=True)
        return
    
    # Create question in database
    question = create_question(user_id, topic, question_text)
    
    # Post to channel
    try:
        from utils import build_channel_question_keyboard
        
        keyboard = build_channel_question_keyboard(question['id'])
        msg = await context.bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=(
                f"<b>#{question['topic'].upper()}</b>\n\n"
                f"{question['text']}\n\n"
                f"<i>by: {get_user(user_id)['display_name']}</i>"
            ),
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        # Update question with message IDs
        update_question(question['id'], message_id=msg.message_id, chat_id=msg.chat_id)
        
        user_state[user_id] = IDLE
        await query.edit_message_text(
            "✅ Question posted!",
            reply_markup=build_main_menu()
        )
    except Exception as e:
        print(f"Error posting to channel: {e}")
        await query.answer("❌ Error posting to channel", show_alert=True)
    
    # Cleanup
    user_state.pop(user_id, None)
    user_data.pop(user_id, None)


async def _handle_vote(query, context: ContextTypes.DEFAULT_TYPE, user_id: int, data: str):
    """Handle upvote/downvote on replies."""
    if data.startswith("vote_up:"):
        parts = data.split(":")
        reply_id = parts[1]
        question_id = parts[2]
        vote_type = "up"
    else:
        parts = data.split(":")
        reply_id = parts[1]
        question_id = parts[2]
        vote_type = "down"
    
    current_vote = get_user_vote(reply_id, user_id)
    
    # If already voted with same type, do nothing
    if current_vote == vote_type:
        await query.answer("Already voted!", show_alert=False)
        return
    
    # If changing vote, update
    if current_vote:
        change_vote(reply_id, user_id, vote_type)
    else:
        add_vote(reply_id, user_id, vote_type)
    
    # Update button display
    await update_reply_vote_display(
        context,
        query.message.chat_id,
        query.message.message_id,
        reply_id,
        question_id,
        user_id
    )
    
    await query.answer(f"{'👍 Liked' if vote_type == 'up' else '👎 Disliked'}", show_alert=False)
