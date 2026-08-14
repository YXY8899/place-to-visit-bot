import os
import secrets
import traceback

from openai import OpenAI
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

NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")
CONVERSATION_NIM_MODEL = os.environ.get(
    "CONVERSATION_NIM_MODEL", "minimaxai/minimax-m3"
)

_client: OpenAI | None = None

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


def _get_client() -> OpenAI:
    global _client
    if not NVIDIA_NIM_API_KEY:
        raise RuntimeError("NVIDIA_NIM_API_KEY is not configured")
    if _client is None:
        _client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_NIM_API_KEY,
            timeout=30,
        )
    return _client


def _generate_question(category: str, previous: str | None) -> str:
    category_guidance = {
        "fun": "playful, imaginative, and easy to answer",
        "curious": "warm, specific, and good for learning something new",
        "deep": "reflective but low-pressure, with no expectation to disclose anything personal",
    }[category]
    previous_note = f"Avoid repeating this recent question: {previous}" if previous else ""
    response = _get_client().chat.completions.create(
        model=CONVERSATION_NIM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate one original conversation question for two adults who are less "
                    "than a year into dating. Keep it kind, inclusive, PG, and free of pressure. "
                    "Do not ask about sex, trauma, finances, marriage, children, or breakups. "
                    "Return only the question, with no label, explanation, quotation marks, or markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Make the question {category_guidance}. {previous_note}".strip()
                ),
            },
        ],
        temperature=0.9,
        max_tokens=100,
    )
    question = (response.choices[0].message.content or "").strip().strip('"')
    if not question or len(question) > 500:
        raise RuntimeError("AI returned an unusable conversation question")
    return question


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
    category, fallback_question = _choose_question(requested_category, previous)
    try:
        question = _generate_question(category, previous)
    except Exception:
        traceback.print_exc()
        question = fallback_question
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
