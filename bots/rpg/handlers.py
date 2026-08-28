import os
import re
import secrets
import traceback
from typing import Any

from openai import OpenAI
from telegram import Bot, Message

from core.config import ALLOWED_USER_IDS
from core.state_store import load_state, save_state
from core.telegram import parse_command, reply


STATE_NAMESPACE = "word_duel"
NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")
WORD_NIM_MODEL = os.environ.get(
    "WORD_NIM_MODEL", os.environ.get("RPG_NIM_MODEL", "minimaxai/minimax-m3")
)

FALLBACK_WORDS = (
    "anchor",
    "balloon",
    "cactus",
    "dolphin",
    "forest",
    "guitar",
    "jigsaw",
    "lantern",
    "meadow",
    "puzzle",
    "rainbow",
    "scooter",
    "sunshine",
    "telescope",
    "whisper",
)

HELP_TEXT = (
    "🔤 Word Duel\n\n"
    "A turn-based word game for two players. Reveal a letter to keep your turn; "
    "miss, and the turn passes. Solve the whole word to win.\n\n"
    "Commands:\n"
    "/newword — start a new word\n"
    "/letter <a-z> — guess one letter on your turn\n"
    "/solve <word> — solve on your turn\n"
    "/status — show the current board\n"
    "/scoreboard — show all-time scores\n"
    "/rematch — start another word with the other player first\n"
    "/endgame — end the current word\n"
    "/whereami — show this chat and topic IDs\n"
    "/help — show this message"
)

_client: OpenAI | None = None


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


def _clean_word(value: str) -> str | None:
    word = value.strip().splitlines()[0].strip("`\"'").lower() if value.strip() else ""
    return word if re.fullmatch(r"[a-z]{4,10}", word) else None


def _generate_word(recent_words: list[str]) -> str:
    try:
        response = _get_client().chat.completions.create(
            model=WORD_NIM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return exactly one common English noun containing 4 to 10 letters. "
                        "Use lowercase letters only. Do not use proper nouns, plurals, spaces, "
                        "hyphens, punctuation, explanations, or markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": "Choose a fresh word for a two-player word guessing game.",
                },
            ],
            temperature=1.0,
            max_tokens=20,
        )
        word = _clean_word(response.choices[0].message.content or "")
        if word and word not in recent_words:
            return word
    except Exception:
        traceback.print_exc()

    available = [word for word in FALLBACK_WORDS if word not in recent_words]
    return secrets.choice(available or FALLBACK_WORDS)


def _message_name(message: Message) -> str:
    user = message.from_user
    return user.first_name or user.username or str(user.id)


def _player_name(game: dict[str, Any], player_id: int | None) -> str:
    if player_id is None:
        return "Nobody"
    return game.get("names", {}).get(str(player_id), f"Player {player_id}")


def _other_player_id(game: dict[str, Any], player_id: int) -> int:
    return next(candidate for candidate in game["players"] if candidate != player_id)


def _is_complete(game: dict[str, Any]) -> bool:
    return all(letter in set(game["guessed"]) for letter in game["word"])


def _board(game: dict[str, Any]) -> str:
    guessed = set(game.get("guessed", []))
    letters = " ".join(
        letter.upper() if letter in guessed else "_" for letter in game["word"]
    )
    guessed_text = ", ".join(letter.upper() for letter in game.get("guessed", []))
    turn = _player_name(game, game.get("turn")) if game.get("active") else "Game over"
    return f"🔤 {letters}\nGuessed: {guessed_text or 'none'}\nTurn: {turn}"


def _load_game(message: Message) -> dict[str, Any] | None:
    return load_state(STATE_NAMESPACE, message.chat_id, message.message_thread_id)


def _save_game(message: Message, game: dict[str, Any]) -> None:
    save_state(STATE_NAMESPACE, message.chat_id, message.message_thread_id, game)


def _remember_player(game: dict[str, Any], message: Message) -> None:
    game.setdefault("names", {})[str(message.from_user.id)] = _message_name(message)


def _new_game(
    message: Message, previous: dict[str, Any] | None, starter_id: int
) -> dict[str, Any]:
    recent_words = (previous or {}).get("recent_words", [])[-20:]
    scores = dict((previous or {}).get("scores", {}))
    players = sorted(ALLOWED_USER_IDS)
    for player_id in players:
        scores.setdefault(str(player_id), 0)

    game = {
        "active": True,
        "word": _generate_word(recent_words),
        "guessed": [],
        "players": players,
        "names": dict((previous or {}).get("names", {})),
        "starter": starter_id,
        "turn": starter_id,
        "scores": scores,
        "recent_words": recent_words,
    }
    _remember_player(game, message)
    game["recent_words"] = (recent_words + [game["word"]])[-20:]
    return game


async def new_word_command(bot: Bot, message: Message):
    if len(ALLOWED_USER_IDS) != 2:
        await reply(bot, message, "Word Duel needs exactly two IDs in ALLOWED_USER_IDS.")
        return
    try:
        existing = _load_game(message)
        if existing and existing.get("active"):
            await reply(bot, message, "A word is already active. Use /status or /endgame first.")
            return
        game = _new_game(message, existing, message.from_user.id)
        _save_game(message, game)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't start a word right now. Please try again.")
        return

    await reply(bot, message, f"🎮 Word Duel started!\n\n{_board(game)}")


async def _current_turn_game(bot: Bot, message: Message) -> dict[str, Any] | None:
    try:
        game = _load_game(message)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't load the game. Please try again.")
        return None
    if not game or not game.get("active"):
        await reply(bot, message, "There is no active word. Start one with /newword.")
        return None

    _remember_player(game, message)
    if message.from_user.id != game.get("turn"):
        await reply(bot, message, f"It's {_player_name(game, game.get('turn'))}'s turn.")
        return None
    return game


def _finish_game(game: dict[str, Any], winner_id: int) -> None:
    game["active"] = False
    game["turn"] = None
    game["winner"] = winner_id
    scores = game.setdefault("scores", {})
    scores[str(winner_id)] = int(scores.get(str(winner_id), 0)) + 1


async def letter_command(bot: Bot, message: Message, arguments: str):
    letter = arguments.lower()
    if not re.fullmatch(r"[a-z]", letter):
        await reply(bot, message, "Guess exactly one letter. Example: /letter e")
        return

    game = await _current_turn_game(bot, message)
    if game is None:
        return
    if letter in game["guessed"]:
        await reply(bot, message, f"{letter.upper()} was already guessed. Try another letter.")
        return

    game["guessed"].append(letter)
    player_id = message.from_user.id
    if letter in game["word"]:
        if _is_complete(game):
            _finish_game(game, player_id)
            _save_game(message, game)
            await reply(
                bot,
                message,
                f"🎉 {_player_name(game, player_id)} revealed the word: {game['word'].upper()}!\n"
                f"🏆 {_player_name(game, player_id)} wins.\n\n{_scoreboard(game)}",
            )
            return
        _save_game(message, game)
        await reply(
            bot,
            message,
            f"Nice! {letter.upper()} is in the word, so {_player_name(game, player_id)} keeps the turn.\n\n{_board(game)}",
        )
        return

    game["turn"] = _other_player_id(game, player_id)
    _save_game(message, game)
    await reply(bot, message, f"No {letter.upper()}.\n\n{_board(game)}")


async def solve_command(bot: Bot, message: Message, arguments: str):
    game = await _current_turn_game(bot, message)
    if game is None:
        return

    guess = _clean_word(arguments)
    if guess is None:
        await reply(bot, message, "Enter one 4-10 letter word. Example: /solve lantern")
        return

    player_id = message.from_user.id
    if guess == game["word"]:
        _finish_game(game, player_id)
        _save_game(message, game)
        await reply(
            bot,
            message,
            f"🎉 Correct — {game['word'].upper()}!\n🏆 {_player_name(game, player_id)} wins.\n\n{_scoreboard(game)}",
        )
        return

    game["turn"] = _other_player_id(game, player_id)
    _save_game(message, game)
    await reply(bot, message, f"Not quite. The turn passes.\n\n{_board(game)}")


def _scoreboard(game: dict[str, Any]) -> str:
    scores = game.get("scores", {})
    lines = ["🏅 All-time score"]
    for player_id in game.get("players", []):
        lines.append(f"{_player_name(game, player_id)}: {scores.get(str(player_id), 0)}")
    return "\n".join(lines)


async def status_command(bot: Bot, message: Message):
    try:
        game = _load_game(message)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't load the game.")
        return
    if not game or not game.get("active"):
        await reply(bot, message, "There is no active word. Start one with /newword.")
        return
    _remember_player(game, message)
    _save_game(message, game)
    await reply(bot, message, _board(game))


async def scoreboard_command(bot: Bot, message: Message):
    try:
        game = _load_game(message)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't load the scores.")
        return
    if not game:
        await reply(bot, message, "No Word Duel scores yet. Start one with /newword.")
        return
    _remember_player(game, message)
    _save_game(message, game)
    await reply(bot, message, _scoreboard(game))


async def rematch_command(bot: Bot, message: Message):
    try:
        previous = _load_game(message)
        if not previous:
            await reply(bot, message, "No previous game found. Start one with /newword.")
            return
        if previous.get("active"):
            await reply(bot, message, "Finish or end the active word before starting a rematch.")
            return
        starter_id = _other_player_id(previous, previous["starter"])
        game = _new_game(message, previous, starter_id)
        _save_game(message, game)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't start the rematch. Please try again.")
        return
    await reply(bot, message, f"🔁 Rematch! {_player_name(game, starter_id)} starts.\n\n{_board(game)}")


async def end_game_command(bot: Bot, message: Message):
    try:
        game = _load_game(message)
        if not game or not game.get("active"):
            await reply(bot, message, "There is no active word to end.")
            return
        game["active"] = False
        game["turn"] = None
        game["winner"] = None
        _remember_player(game, message)
        _save_game(message, game)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't end the game. Please try again.")
        return
    await reply(bot, message, "Game ended. Scores are kept; start another with /newword.")


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
    elif command == "newword":
        await new_word_command(bot, message)
    elif command == "letter":
        await letter_command(bot, message, arguments)
    elif command == "solve":
        await solve_command(bot, message, arguments)
    elif command == "status":
        await status_command(bot, message)
    elif command == "scoreboard":
        await scoreboard_command(bot, message)
    elif command == "rematch":
        await rematch_command(bot, message)
    elif command == "endgame":
        await end_game_command(bot, message)
    elif command == "whereami":
        await whereami_command(bot, message)
