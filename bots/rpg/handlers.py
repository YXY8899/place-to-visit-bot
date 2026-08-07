import json
import os
import traceback
from typing import Any

from openai import OpenAI
from telegram import Bot, Message

from core.state_store import clear_state, load_state, save_state
from core.telegram import parse_command, reply


NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")
RPG_NIM_MODEL = os.environ.get("RPG_NIM_MODEL", "minimaxai/minimax-m3")

_client: OpenAI | None = None

HELP_TEXT = (
    "🎲 Two-Player AI RPG\n\n"
    "A cooperative story with the bot as game master.\n\n"
    "Commands:\n"
    "/newgame <theme> — create a new adventure\n"
    "/join — join as the second player\n"
    "/act <action> — take your turn\n"
    "/status — show the current scene and turn\n"
    "/endgame — end the current adventure\n"
    "/whereami — show this chat and topic IDs\n"
    "/help — show this message"
)

SYSTEM_PROMPT = (
    "You are a warm, imaginative game master for exactly two cooperative players. "
    "Keep the adventure PG-13, playful, inclusive, and suitable for a couple. "
    "Never control the players' characters or decide their actions for them. "
    "Respond in 2-4 short paragraphs, resolve the submitted action fairly, then end "
    "with one clear situation or choice for the next player. Do not use markdown tables."
)


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


def _player(message: Message) -> dict[str, Any]:
    user = message.from_user
    return {
        "id": user.id,
        "name": user.first_name or user.username or str(user.id),
    }


def _load_game(message: Message) -> dict[str, Any] | None:
    return load_state("rpg", message.chat_id, message.message_thread_id)


def _save_game(message: Message, game: dict[str, Any]) -> None:
    save_state("rpg", message.chat_id, message.message_thread_id, game)


def _generate_story(instruction: str, game: dict[str, Any]) -> str:
    context = {
        "theme": game["theme"],
        "players": [player["name"] for player in game["players"]],
        "current_scene": game.get("scene", ""),
        "recent_history": game.get("history", [])[-8:],
    }
    response = _get_client().chat.completions.create(
        model=RPG_NIM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Game state:\n{json.dumps(context, ensure_ascii=False)}\n\n{instruction}",
            },
        ],
        temperature=0.8,
        max_tokens=500,
    )
    return (response.choices[0].message.content or "").strip()


async def new_game_command(bot: Bot, message: Message, arguments: str):
    theme = arguments or "a mysterious adventure in modern Singapore"
    try:
        existing = _load_game(message)
        if existing and existing.get("active"):
            await reply(bot, message, "A game is already active. Use /endgame before starting another.")
            return

        creator = _player(message)
        game = {
            "active": True,
            "theme": theme[:300],
            "players": [creator],
            "turn": 0,
            "scene": "",
            "history": [],
        }
        _save_game(message, game)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't create the game. Check that the bot_state database migration has been applied.")
        return

    await reply(
        bot,
        message,
        f"🎲 New adventure: {theme}\n\n{creator['name']} is Player 1. The other player can join with /join.",
    )


async def join_command(bot: Bot, message: Message):
    try:
        game = _load_game(message)
        if not game or not game.get("active"):
            await reply(bot, message, "There is no active game. Start one with /newgame <theme>.")
            return

        joining_player = _player(message)
        if any(player["id"] == joining_player["id"] for player in game["players"]):
            await reply(bot, message, "You're already in this adventure.")
            return
        if len(game["players"]) >= 2:
            await reply(bot, message, "This adventure already has two players.")
            return

        game["players"].append(joining_player)
        intro = _generate_story(
            "Introduce the adventure, establish the opening scene, and invite Player 1 to act first.",
            game,
        )
        game["scene"] = intro
        game["history"].append({"type": "narration", "text": intro})
        _save_game(message, game)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't start the story. Check the AI key and try /join again.")
        return

    await reply(
        bot,
        message,
        f"🧭 {joining_player['name']} joined as Player 2.\n\n{intro}\n\nTurn: {game['players'][0]['name']}",
    )


async def act_command(bot: Bot, message: Message, arguments: str):
    if not arguments:
        await reply(bot, message, "Describe what your character does. Example: /act inspect the locked door")
        return
    if len(arguments) > 600:
        await reply(bot, message, "Keep each action under 600 characters.")
        return

    try:
        game = _load_game(message)
        if not game or not game.get("active"):
            await reply(bot, message, "There is no active game. Start one with /newgame <theme>.")
            return
        if len(game.get("players", [])) < 2:
            await reply(bot, message, "The second player needs to /join before the adventure begins.")
            return

        current_player = game["players"][game["turn"]]
        if message.from_user.id != current_player["id"]:
            await reply(bot, message, f"It's {current_player['name']}'s turn.")
            return

        narrative = _generate_story(
            f"{current_player['name']} attempts this action: {arguments}",
            game,
        )
        game["history"].extend(
            [
                {"type": "action", "player": current_player["name"], "text": arguments},
                {"type": "narration", "text": narrative},
            ]
        )
        game["history"] = game["history"][-16:]
        game["scene"] = narrative
        game["turn"] = (game["turn"] + 1) % 2
        _save_game(message, game)
        next_player = game["players"][game["turn"]]
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "The game master couldn't resolve that action. Your turn was not consumed; please try again.")
        return

    await reply(bot, message, f"🎭 {narrative}\n\nTurn: {next_player['name']}")


async def status_command(bot: Bot, message: Message):
    try:
        game = _load_game(message)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't load the game state.")
        return
    if not game or not game.get("active"):
        await reply(bot, message, "There is no active game.")
        return

    players = ", ".join(player["name"] for player in game.get("players", []))
    current_turn = (
        game["players"][game["turn"]]["name"]
        if len(game.get("players", [])) == 2
        else "Waiting for Player 2"
    )
    scene = game.get("scene") or "The adventure has not begun yet."
    await reply(
        bot,
        message,
        f"🎲 Theme: {game['theme']}\nPlayers: {players}\nTurn: {current_turn}\n\nCurrent scene:\n{scene[:1800]}",
    )


async def end_game_command(bot: Bot, message: Message):
    try:
        clear_state("rpg", message.chat_id, message.message_thread_id)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "I couldn't end the game cleanly. Please try again.")
        return
    await reply(bot, message, "🏁 Adventure ended. Start a new one anytime with /newgame <theme>.")


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
    elif command == "newgame":
        await new_game_command(bot, message, arguments)
    elif command == "join":
        await join_command(bot, message)
    elif command == "act":
        await act_command(bot, message, arguments)
    elif command == "status":
        await status_command(bot, message)
    elif command == "endgame":
        await end_game_command(bot, message)
    elif command == "whereami":
        await whereami_command(bot, message)
