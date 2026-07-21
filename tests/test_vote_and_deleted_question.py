import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

import database as db
from handlers.start import _show_question
from handlers.buttons import button_handler


class TestVoteToggleAndDeletedQuestion(unittest.IsolatedAsyncioTestCase):

    @patch("database._db")
    async def test_cast_vote_toggle_upvote(self, mock_db):
        mock_votes = AsyncMock()
        mock_replies = AsyncMock()
        mock_users = AsyncMock()

        db_mock = MagicMock()
        db_mock.votes = mock_votes
        db_mock.replies = mock_replies
        db_mock.users = mock_users
        mock_db.return_value = db_mock

        target_id = ObjectId()
        user_id = 100
        author_id = 200

        # Scenario 1: First vote (Upvote)
        mock_votes.find_one.return_value = None
        mock_replies.find_one_and_update.return_value = {
            "_id": target_id, "author_id": author_id, "upvotes": 1, "downvotes": 0
        }

        changed, new_dir = await db.cast_vote(target_id, "reply", user_id, "up")
        self.assertTrue(changed)
        self.assertEqual(new_dir, "up")
        mock_votes.update_one.assert_called()

        # Scenario 2: Toggle Upvote off
        mock_votes.find_one.return_value = {"direction": "up"}
        mock_replies.find_one_and_update.return_value = {
            "_id": target_id, "author_id": author_id, "upvotes": 0, "downvotes": 0
        }

        changed, new_dir = await db.cast_vote(target_id, "reply", user_id, "up")
        self.assertTrue(changed)
        self.assertIsNone(new_dir)
        mock_votes.delete_one.assert_called_with({"target_id": target_id, "user_id": user_id})

    @patch("database._db")
    async def test_cast_vote_toggle_downvote(self, mock_db):
        mock_votes = AsyncMock()
        mock_replies = AsyncMock()
        mock_users = AsyncMock()

        db_mock = MagicMock()
        db_mock.votes = mock_votes
        db_mock.replies = mock_replies
        db_mock.users = mock_users
        mock_db.return_value = db_mock

        target_id = ObjectId()
        user_id = 100
        author_id = 200

        # Scenario 3: Toggle Downvote off
        mock_votes.find_one.return_value = {"direction": "down"}
        mock_replies.find_one_and_update.return_value = {
            "_id": target_id, "author_id": author_id, "upvotes": 0, "downvotes": 0
        }

        changed, new_dir = await db.cast_vote(target_id, "reply", user_id, "down")
        self.assertTrue(changed)
        self.assertIsNone(new_dir)
        mock_votes.delete_one.assert_called_with({"target_id": target_id, "user_id": user_id})

    @patch("database._db")
    async def test_cast_vote_switch_vote(self, mock_db):
        mock_votes = AsyncMock()
        mock_replies = AsyncMock()
        mock_users = AsyncMock()

        db_mock = MagicMock()
        db_mock.votes = mock_votes
        db_mock.replies = mock_replies
        db_mock.users = mock_users
        mock_db.return_value = db_mock

        target_id = ObjectId()
        user_id = 100
        author_id = 200

        # Upvote -> Downvote switch
        mock_votes.find_one.return_value = {"direction": "up"}
        mock_replies.find_one_and_update.return_value = {
            "_id": target_id, "author_id": author_id, "upvotes": 0, "downvotes": 1
        }

        changed, new_dir = await db.cast_vote(target_id, "reply", user_id, "down")
        self.assertTrue(changed)
        self.assertEqual(new_dir, "down")
        mock_votes.update_one.assert_called()

    @patch("database._db")
    async def test_get_question_returns_none_when_deleted(self, mock_db):
        mock_questions = AsyncMock()
        db_mock = MagicMock()
        db_mock.questions = mock_questions
        mock_db.return_value = db_mock

        qid = ObjectId()
        mock_questions.find_one.return_value = None

        res = await db.get_question(qid)
        self.assertIsNone(res)
        mock_questions.find_one.assert_called_with(
            {"_id": qid, "is_deleted": False, "$or": [{"status": {"$exists": False}}, {"status": "approved"}]}
        )

    @patch("database.get_question", new_callable=AsyncMock)
    async def test_show_question_blocked_if_deleted(self, mock_get_question):
        mock_get_question.return_value = None

        update = MagicMock()
        update.message = AsyncMock()
        context = MagicMock()

        await _show_question(update, context, user_id=1, chat_id=10, question_id=str(ObjectId()))
        update.message.reply_text.assert_called_with("❌ This question is no longer available.")

    @patch("database.get_or_create_user", new_callable=AsyncMock)
    @patch("database.get_question", new_callable=AsyncMock)
    async def test_button_handler_blocks_deleted_question_operations(self, mock_get_question, mock_get_user):
        mock_get_user.return_value = {"is_banned": False}
        mock_get_question.return_value = None

        update = MagicMock()
        query = AsyncMock()
        query.from_user.id = 100
        query.message.chat_id = 10
        query.message.message_id = 50
        query.data = f"vote_up:reply123:{ObjectId()}"
        update.callback_query = query
        context = MagicMock()

        await button_handler(update, context)
        query.answer.assert_called_with("❌ This question is no longer available.", show_alert=True)


if __name__ == "__main__":
    unittest.main()
