import asyncio
import unittest
from unittest.mock import patch

from bots.conversation.handlers import QUESTIONS, _choose_question
from bots.rpg.handlers import _is_complete, letter_command, solve_command
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

    def test_ai_question_is_used_and_saved_when_available(self):
        class FakeBot:
            def __init__(self):
                self.messages = []

            async def send_message(self, **kwargs):
                self.messages.append(kwargs)

        class FakeMessage:
            chat_id = -100123
            message_thread_id = 42

        bot = FakeBot()
        message = FakeMessage()
        with (
            patch("bots.conversation.handlers.load_state", return_value=None),
            patch("bots.conversation.handlers.save_state") as save_state,
            patch(
                "bots.conversation.handlers._generate_question",
                return_value="What small moment made you smile this week?",
            ),
        ):
            asyncio.run(
                __import__("bots.conversation.handlers", fromlist=["question_command"])
                .question_command(bot, message, "fun")
            )

        self.assertIn("What small moment made you smile this week?", bot.messages[0]["text"])
        self.assertEqual(save_state.call_args.args[3]["category"], "fun")


class WordDuelTest(unittest.TestCase):
    @staticmethod
    def _message(user_id: int):
        class FakeUser:
            def __init__(self, value: int):
                self.id = value
                self.first_name = f"Player {value}"
                self.username = None

        class FakeMessage:
            chat_id = -100123
            message_thread_id = 42

            def __init__(self, value: int):
                self.from_user = FakeUser(value)

        return FakeMessage(user_id)

    @staticmethod
    def _bot():
        class FakeBot:
            def __init__(self):
                self.messages = []

            async def send_message(self, **kwargs):
                self.messages.append(kwargs)

        return FakeBot()

    @staticmethod
    def _game():
        return {
            "active": True,
            "word": "apple",
            "guessed": [],
            "players": [1, 2],
            "names": {"1": "Player 1", "2": "Player 2"},
            "starter": 1,
            "turn": 1,
            "scores": {"1": 0, "2": 0},
            "recent_words": ["apple"],
        }

    def test_correct_letter_keeps_the_current_turn(self):
        game = self._game()
        bot = self._bot()
        with (
            patch("bots.rpg.handlers.load_state", return_value=game),
            patch("bots.rpg.handlers.save_state") as save_state,
        ):
            asyncio.run(letter_command(bot, self._message(1), "p"))

        self.assertEqual(game["turn"], 1)
        self.assertIn("p", game["guessed"])
        self.assertTrue(save_state.called)

    def test_solve_is_rejected_when_it_is_not_the_players_turn(self):
        game = self._game()
        bot = self._bot()
        with (
            patch("bots.rpg.handlers.load_state", return_value=game),
            patch("bots.rpg.handlers.save_state") as save_state,
        ):
            asyncio.run(solve_command(bot, self._message(2), "apple"))

        self.assertIn("It's Player 1's turn.", bot.messages[0]["text"])
        save_state.assert_not_called()

    def test_revealing_all_letters_completes_the_word(self):
        game = self._game()
        game["guessed"] = ["a", "p", "l", "e"]
        self.assertTrue(_is_complete(game))


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
