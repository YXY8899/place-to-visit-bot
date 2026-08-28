"""Gunicorn entry point for the three-bot couples hub."""

import asyncio

from bots.conversation import handle_message as handle_conversation
from bots.places import handle_message as handle_places
from bots.rpg import handle_message as handle_rpg
from core.config import (
    ALLOWED_USER_IDS,
    CONVERSATION_BOT_TOKEN,
    CONVERSATION_TOPIC_ID,
    COUPLE_CHAT_ID,
    PLACE_BOT_TOKEN,
    PLACE_TOPIC_ID,
    RPG_BOT_TOKEN,
    RPG_TOPIC_ID,
    WEBHOOK_URL,
)
from core.runtime import BotRegistration, BotRuntime


CONVERSATION_COMMANDS = (
    ("question", "Get a conversation prompt"),
    ("next", "Replace the current prompt"),
    ("whereami", "Show this chat and topic IDs"),
    ("help", "Show help"),
)

WORD_DUEL_COMMANDS = (
    ("newword", "Start a new Word Duel"),
    ("letter", "Guess a letter on your turn"),
    ("solve", "Solve the word on your turn"),
    ("status", "Show the current word"),
    ("scoreboard", "Show all-time scores"),
    ("rematch", "Start another word"),
    ("endgame", "End the current word"),
    ("whereami", "Show this chat and topic IDs"),
    ("help", "Show help"),
)


if not ALLOWED_USER_IDS:
    raise RuntimeError(
        "ALLOWED_USER_IDS must list the two Telegram user IDs allowed to use the bots."
    )

runtime = BotRuntime(
    registrations=[
        BotRegistration("places", PLACE_BOT_TOKEN, handle_places, PLACE_TOPIC_ID),
        BotRegistration(
            "conversation",
            CONVERSATION_BOT_TOKEN,
            handle_conversation,
            CONVERSATION_TOPIC_ID,
            commands=CONVERSATION_COMMANDS,
        ),
        BotRegistration(
            "rpg",
            RPG_BOT_TOKEN,
            handle_rpg,
            RPG_TOPIC_ID,
            commands=WORD_DUEL_COMMANDS,
        ),
    ],
    webhook_url=WEBHOOK_URL,
    chat_id=COUPLE_CHAT_ID,
    allowed_user_ids=ALLOWED_USER_IDS,
)

flask_app = runtime.create_flask_app()
asyncio.run(runtime.register_webhooks())
