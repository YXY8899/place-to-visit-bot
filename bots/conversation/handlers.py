import secrets
import traceback

from telegram import Bot, Message

from core.state_store import load_state, save_state
from core.telegram import parse_command, reply


QUESTIONS = {
    "fun": [
        "What tiny, unnecessary purchase always makes you happy?",
        "If tonight had a theme song, what would it be?",
        "Which food could you happily eat three days in a row?",
        "What harmless opinion would you defend far too passionately?",
        "If we opened a ridiculous business together, what would it sell?",
        "Which fictional world would be the best place for a weekend trip?",
    ],
    "curious": [
        "What is something you have always wanted to learn for fun?",
        "What does your ideal completely unplanned day look like?",
        "Which part of your childhood would you enjoy showing me?",
        "What kind of compliment tends to stay with you?",
        "What is a small tradition you would like to start someday?",
        "What place feels most like home to you, and why?",
    ],
    "deep": [
        "When do you feel most understood by another person?",
        "What helps you feel cared for when you have had a difficult day?",
        "What is something you are currently trying to become better at?",
        "What does a healthy amount of independence look like to you?",
        "Which value has become more important to you as you have grown older?",
        "What kind of future experience would you love to share with someone?",
    ],
}

HELP_TEXT = (
    "✨ Conversation Spark\n\n"
    "A low-pressure question bot for getting to know each other.\n\n"
    "Commands:\n"
    "/question — choose a random prompt\n"
    "/question fun — keep it playful\n"
    "/question curious — learn something new\n"
    "/question deep — go a little deeper\n"
    "/next — replace the current prompt\n"
    "/whereami — show this chat and topic IDs\n"
    "/help — show this message"
)


def _choose_question(category: str, previous: str | None) -> tuple[str, str]:
    selected_category = category if category in QUESTIONS else secrets.choice(list(QUESTIONS))
    candidates = [question for question in QUESTIONS[selected_category] if question != previous]
    return selected_category, secrets.choice(candidates or QUESTIONS[selected_category])


async def question_command(bot: Bot, message: Message, arguments: str):
    previous = None
    previous_category = None
    try:
        state = load_state("conversation", message.chat_id, message.message_thread_id)
        previous = state.get("question") if state else None
        previous_category = state.get("category") if state else None
    except Exception:
        traceback.print_exc()

    requested_category = arguments.lower() or previous_category or ""
    category, question = _choose_question(requested_category, previous)
    try:
        save_state(
            "conversation",
            message.chat_id,
            message.message_thread_id,
            {"category": category, "question": question},
        )
    except Exception:
        traceback.print_exc()

    await reply(
        bot,
        message,
        f"✨ {category.title()} question\n\n{question}\n\nTake turns answering — curiosity first, no scoring.",
    )


async def whereami_command(bot: Bot, message: Message):
    topic = message.message_thread_id
    await reply(
        bot,
        message,
        f"Chat ID: {message.chat_id}\nTopic ID: {topic if topic is not None else 'General'}",
    )


async def handle_message(bot: Bot, message: Message):
    parsed = parse_command(message.text or "")
    if parsed is None:
        return
    command, arguments = parsed
    if command in {"start", "help"}:
        await reply(bot, message, HELP_TEXT)
    elif command in {"question", "next"}:
        await question_command(bot, message, arguments)
    elif command == "whereami":
        await whereami_command(bot, message)
