import asyncio
import os
import re
import threading
import traceback

from flask import Flask, request
from telegram import Bot, Update

import db
import nearby as nearby_mod

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")


def optional_int_env(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    return int(value) if value else None


# Optional locks for deploying this bot to a single forum topic. Leave either
# value unset while discovering the IDs, then set both in Render.
PLACE_CHAT_ID = optional_int_env("PLACE_CHAT_ID")
PLACE_TOPIC_ID = optional_int_env("PLACE_TOPIC_ID")
ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if uid.strip().isdigit()
)

flask_app = Flask(__name__)


# ---------------------------------------------------------------------------
# MarkdownV2 helper
# ---------------------------------------------------------------------------

def escape_md(text: str) -> str:
    return re.sub(r'([\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!])', r'\\\1', text)


async def send_message(
    bot: Bot, chat_id: int, text: str, thread_id: int | None = None, **kwargs
):
    """Send a response back into the forum topic that received the command."""
    if thread_id is not None:
        kwargs["message_thread_id"] = thread_id
    await bot.send_message(chat_id=chat_id, text=text, **kwargs)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start_command(bot: Bot, chat_id: int, thread_id: int | None):
    await send_message(
        bot,
        chat_id,
        text=(
            "ðŸ‘‹ Place to Visit Bot\n\n"
            "Save places and restaurants you want to visit.\n\n"
            "Commands:\n"
            "/add <place name> â€” queue a place\n"
            "/list â€” show all saved places\n"
            "/list <tag1>, <tag2> â€” filter by tags (must match all)\n"
            "/detail <place name> â€” show full details of a place\n"
            "/nearby <location> â€” top 3 places by public transit time\n"
            "/visited <place name> â€” mark a place as visited\n"
            "/tags â€” show all available tags\n"
            "/pending â€” show places waiting to be enriched\n"
            "/delete <place name> â€” remove a place\n"
            "/whereami â€” show this chat and topic IDs\n"
            "/help â€” show this message"
        ),
        thread_id=thread_id,
    )


async def whereami_command(bot: Bot, chat_id: int, thread_id: int | None):
    await send_message(
        bot,
        chat_id,
        f"Chat ID: {chat_id}\nTopic ID: {thread_id if thread_id is not None else 'General'}",
        thread_id,
    )


async def add_command(bot: Bot, chat_id: int, thread_id: int | None, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message(bot, chat_id, "Please provide a place name. Example: /add Eiffel Tower", thread_id)
        return
    name = parts[1].strip()
    try:
        db.queue_place(name)
        await send_message(bot, chat_id, f"âœ… {name} added to your queue! It will be enriched and saved shortly.", thread_id)
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to save place. Please try again.", thread_id)


async def list_command(bot: Bot, chat_id: int, thread_id: int | None, text: str):
    parts = text.split(None, 1)
    tags = [t.strip() for t in parts[1].split(",")] if len(parts) > 1 and parts[1].strip() else []

    try:
        places = db.get_all_places(tags=tags if tags else None)
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to retrieve places. Please try again.", thread_id)
        return

    if not places:
        if tags:
            tag_str = ", ".join(tags)
            await send_message(bot, chat_id, f"No places found with tags: {tag_str}.", thread_id)
        else:
            await send_message(bot, chat_id, "You have no saved places yet. Use /add <name> to get started.", thread_id)
        return

    blocks = []
    for place in places:
        name = place.get("name", "")
        maps_link = place.get("maps_link", "")
        details = place.get("details", "")
        address = place.get("address", "")
        price_range = place.get("price_range", "")
        tags_val = place.get("tags") or []

        name_esc = escape_md(name) if name else "Unknown"
        details_esc = escape_md(details) if details else "No details available\\."
        address_esc = escape_md(address) if address else ""
        price_esc = escape_md(price_range) if price_range else ""
        tags_esc = escape_md(", ".join(tags_val)) if tags_val else ""

        lines = [f"ðŸ“ *{name_esc}*"]
        if tags_esc:
            lines.append(f"ðŸ· {tags_esc}")
        if price_esc:
            lines.append(f"ðŸ’° {price_esc}")
        if address_esc:
            lines.append(f"ðŸ“® {address_esc}")
        if maps_link:
            lines.append(f"ðŸ—º [Open in Google Maps]({maps_link})")
        lines.append("â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€")
        blocks.append("\n".join(lines))

    for i in range(0, len(blocks), 5):
        chunk = "\n\n".join(blocks[i : i + 5])
        await send_message(bot, chat_id, chunk, thread_id, parse_mode="MarkdownV2")


async def detail_command(bot: Bot, chat_id: int, thread_id: int | None, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message(bot, chat_id, "Please provide a place name. Example: /detail Lau Pa Sat", thread_id)
        return
    name = parts[1].strip()
    try:
        place = db.get_place(name)
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to retrieve place. Please try again.", thread_id)
        return

    if not place:
        await send_message(bot, chat_id, f"No place found matching \"{name}\".", thread_id)
        return

    maps_link = place.get("maps_link", "")
    details = place.get("details", "")
    address = place.get("address", "")
    price_range = place.get("price_range", "")
    tags_val = place.get("tags") or []

    name_esc = escape_md(place.get("name", name))
    details_esc = escape_md(details) if details else "No details available\\."
    address_esc = escape_md(address) if address else ""
    price_esc = escape_md(price_range) if price_range else ""
    tags_esc = escape_md(", ".join(tags_val)) if tags_val else ""

    lines = [f"ðŸ“ *{name_esc}*"]
    if tags_esc:
        lines.append(f"ðŸ· {tags_esc}")
    if price_esc:
        lines.append(f"ðŸ’° {price_esc}")
    if address_esc:
        lines.append(f"ðŸ“® {address_esc}")
    if maps_link:
        lines.append(f"ðŸ—º [Open in Google Maps]({maps_link})")
    lines.append(f"ðŸ“ {details_esc}")

    await send_message(bot, chat_id, "\n".join(lines), thread_id, parse_mode="MarkdownV2")


async def nearby_command(bot: Bot, chat_id: int, thread_id: int | None, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message(bot, chat_id, "Please provide a location. Example: /nearby Bugis MRT", thread_id)
        return

    raw_location = parts[1].strip()
    await send_message(bot, chat_id, "ðŸ” Finding nearby places via public transport...", thread_id)

    try:
        places = db.get_all_places()
        parsed_location, results = nearby_mod.find_nearby(raw_location, places, top_n=3)
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to find nearby places. Please try again.", thread_id)
        return

    if not results:
        await send_message(
            bot,
            chat_id,
            f"No nearby places found from {raw_location}. Places need addresses to be searchable.",
            thread_id,
        )
        return

    blocks = []
    for i, place in enumerate(results, 1):
        name = place.get("name", "")
        maps_link = place.get("maps_link", "")
        address = place.get("address", "")
        price_range = place.get("price_range", "")
        tags_val = place.get("tags") or []
        duration_text = place.get("duration_text", "")

        name_esc = escape_md(name)
        address_esc = escape_md(address) if address else ""
        price_esc = escape_md(price_range) if price_range else ""
        tags_esc = escape_md(", ".join(tags_val)) if tags_val else ""
        duration_esc = escape_md(duration_text)

        lines = [f"{i}\\. ðŸ“ *{name_esc}* â€” ðŸšŒ {duration_esc}"]
        if tags_esc:
            lines.append(f"   ðŸ· {tags_esc}")
        if price_esc:
            lines.append(f"   ðŸ’° {price_esc}")
        if address_esc:
            lines.append(f"   ðŸ“® {address_esc}")
        if maps_link:
            lines.append(f"   ðŸ—º [Open in Google Maps]({maps_link})")
        blocks.append("\n".join(lines))

    header = f"ðŸšŒ *Top 3 places from {escape_md(parsed_location)}:*\n\n"
    await send_message(bot, chat_id, header + "\n\n".join(blocks), thread_id, parse_mode="MarkdownV2")


async def pending_command(bot: Bot, chat_id: int, thread_id: int | None):
    try:
        pending = db.get_pending()
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to retrieve queue. Please try again.", thread_id)
        return

    if not pending:
        await send_message(bot, chat_id, "No places in the queue.", thread_id)
        return

    lines = [f"â³ *{len(pending)} place(s) pending enrichment:*"]
    for i, item in enumerate(pending, 1):
        lines.append(escape_md(f"{i}. {item['name']}"))
    await send_message(bot, chat_id, "\n".join(lines), thread_id, parse_mode="MarkdownV2")


async def tags_command(bot: Bot, chat_id: int, thread_id: int | None):
    try:
        tags = db.get_all_tags()
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to retrieve tags. Please try again.", thread_id)
        return

    if not tags:
        await send_message(bot, chat_id, "No tags found. Add some places first.", thread_id)
        return

    tag_list = "\n".join(f"â€¢ {escape_md(t)}" for t in tags)
    await send_message(bot, chat_id, f"ðŸ· *Available tags:*\n{tag_list}", thread_id, parse_mode="MarkdownV2")


async def visited_command(bot: Bot, chat_id: int, thread_id: int | None, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message(bot, chat_id, "Please provide a place name. Example: /visited Lau Pa Sat", thread_id)
        return
    name = parts[1].strip()
    try:
        marked = db.mark_visited(name)
        await send_message(bot, chat_id, f"âœ… {name} marked as visited!" if marked else "Place not found.", thread_id)
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to update place. Please try again.", thread_id)


async def delete_command(bot: Bot, chat_id: int, thread_id: int | None, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message(bot, chat_id, "Please provide a place name. Example: /delete Eiffel Tower", thread_id)
        return
    name = parts[1].strip()
    try:
        deleted = db.delete_place(name)
        await send_message(bot, chat_id, "Deleted!" if deleted else "Place not found.", thread_id)
    except Exception:
        traceback.print_exc()
        await send_message(bot, chat_id, "Failed to delete place. Please try again.", thread_id)


# ---------------------------------------------------------------------------
# Core update dispatcher
# ---------------------------------------------------------------------------

async def handle_update(data: dict):
    async with Bot(token=BOT_TOKEN) as bot:
        update = Update.de_json(data, bot)
        msg = update.message
        if not msg or not msg.text:
            return

        user_id = msg.from_user.id if msg.from_user else None
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            return

        text = msg.text.strip()
        chat_id = msg.chat_id
        thread_id = msg.message_thread_id

        if PLACE_CHAT_ID is not None and chat_id != PLACE_CHAT_ID:
            return
        if PLACE_TOPIC_ID is not None and thread_id != PLACE_TOPIC_ID:
            return

        if text.startswith("/start") or text.startswith("/help"):
            await start_command(bot, chat_id, thread_id)
        elif text.startswith("/whereami"):
            await whereami_command(bot, chat_id, thread_id)
        elif text.startswith("/add"):
            await add_command(bot, chat_id, thread_id, text)
        elif text.startswith("/list"):
            await list_command(bot, chat_id, thread_id, text)
        elif text.startswith("/detail"):
            await detail_command(bot, chat_id, thread_id, text)
        elif text.startswith("/nearby"):
            await nearby_command(bot, chat_id, thread_id, text)
        elif text.startswith("/pending"):
            await pending_command(bot, chat_id, thread_id)
        elif text.startswith("/tags"):
            await tags_command(bot, chat_id, thread_id)
        elif text.startswith("/visited"):
            await visited_command(bot, chat_id, thread_id, text)
        elif text.startswith("/delete"):
            await delete_command(bot, chat_id, thread_id, text)


# ---------------------------------------------------------------------------
# Webhook registration at startup
# ---------------------------------------------------------------------------

async def _set_webhook():
    async with Bot(token=BOT_TOKEN) as bot:
        await bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
        print(f"Webhook set to {WEBHOOK_URL}/webhook/{BOT_TOKEN}", flush=True)


asyncio.run(_set_webhook())


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@flask_app.route("/", methods=["GET"])
def health():
    return "Bot is alive!", 200


@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        threading.Thread(
            target=lambda: asyncio.run(handle_update(data)),
            daemon=True,
        ).start()
    except Exception:
        traceback.print_exc()
    return "ok", 200

