import unittest
from unittest.mock import patch

from bots.conversation.handlers import QUESTIONS, _choose_question
from core.runtime import BotRegistration
from core.state_store import _headers_for
from core.telegram import escape_markdown, parse_command


async def _handler(_bot, _message):
    return None


class TelegramHelpersTest(unittest.TestCase):
    def test_parse_group_command_with_bot_username(self):
        self.assertEqual(
            parse_command("/question@conversation_bot curious"),
            ("question", "curious"),
        )

    def test_non_command_is_ignored(self):
        self.assertIsNone(parse_command("hello"))

    def test_markdown_v2_characters_are_escaped(self):
        self.assertEqual(escape_markdown("A.B!"), r"A\.B\!")


class ConversationQuestionTest(unittest.TestCase):
    def test_category_is_respected_and_previous_question_is_not_repeated(self):
        previous = QUESTIONS["fun"][0]
        with patch("bots.conversation.handlers.secrets.choice", side_effect=lambda values: values[0]):
            category, question = _choose_question("fun", previous)
        self.assertEqual(category, "fun")
        self.assertNotEqual(question, previous)
        self.assertIn(question, QUESTIONS["fun"])


class WebhookRegistrationTest(unittest.TestCase):
    def test_secret_is_stable_and_does_not_expose_token(self):
        registration = BotRegistration("rpg", "123:secret", _handler)
        self.assertEqual(len(registration.webhook_secret), 64)
        self.assertNotIn("123:secret", registration.webhook_secret)

    def test_registration_keeps_command_menu(self):
        registration = BotRegistration(
            "rpg",
            "123:secret",
            _handler,
            commands=(("help", "Show help"),),
        )
        self.assertEqual(registration.commands, (("help", "Show help"),))


class SupabaseKeyTest(unittest.TestCase):
    def test_new_secret_key_is_sent_only_as_apikey(self):
        headers = _headers_for("sb_secret_example")
        self.assertEqual(headers["apikey"], "sb_secret_example")
        self.assertNotIn("Authorization", headers)

    def test_legacy_key_retains_authorization_header(self):
        headers = _headers_for("eyJ.legacy.key")
        self.assertEqual(headers["Authorization"], "Bearer eyJ.legacy.key")


if __name__ == "__main__":
    unittest.main()
