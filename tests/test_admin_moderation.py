import unittest

from admin import build_channel_post_url, parse_user_id_arg
from utils import (
    SimpleRateLimiter,
    build_channel_question_text,
    kb_admin_report,
    normalize_content_rating,
    sanitize_text_content,
)


class ParseUserIdArgTests(unittest.TestCase):
    def test_accepts_numeric_ids(self) -> None:
        self.assertEqual(parse_user_id_arg("12345"), 12345)

    def test_rejects_non_numeric_input(self) -> None:
        self.assertIsNone(parse_user_id_arg("abc"))

    def test_rejects_empty_input(self) -> None:
        self.assertIsNone(parse_user_id_arg(""))

    def test_admin_report_buttons_use_short_callback_data(self) -> None:
        keyboard = kb_admin_report("507f191e810c19729de860ea", "reply", "507f191e810c19729de860eb")
        data = keyboard.inline_keyboard[0][0].callback_data
        self.assertLessEqual(len(data.encode("utf-8")), 64)

    def test_build_channel_post_url_formats_telegram_link(self) -> None:
        self.assertEqual(build_channel_post_url("@examplechannel", 42), "https://t.me/examplechannel/42")

    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = SimpleRateLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow("user1", "question"))
        self.assertTrue(limiter.allow("user1", "question"))
        self.assertFalse(limiter.allow("user1", "question"))

    def test_sanitize_text_content_escapes_html(self) -> None:
        self.assertEqual(sanitize_text_content("<b>ok</b>"), "&lt;b&gt;ok&lt;/b&gt;")

    def test_content_rating_defaults_to_normal(self) -> None:
        self.assertEqual(normalize_content_rating(None), "normal")
        self.assertEqual(normalize_content_rating(""), "normal")
        self.assertEqual(normalize_content_rating("unknown"), "normal")

    def test_sensitive_channel_preview_hides_question_text(self) -> None:
        question = {
            "topic": "health",
            "text": "This is a secret question",
            "reply_count": 0,
            "content_rating": "sensitive",
        }
        text = build_channel_question_text(question, {})
        self.assertIn("explicit content", text.lower())
        self.assertNotIn("This is a secret question", text)
        self.assertIn("Answers", text)


if __name__ == "__main__":
    unittest.main()
