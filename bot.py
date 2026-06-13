import asyncio
import os
import re
import traceback

from flask import Flask, request
from telegram import Bot, Update

import db

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
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


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start_command(bot: Bot, chat_id: int):
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "👋 Place to Visit Bot\n\n"
            "Save places and restaurants you want to visit.\n\n"
            "Commands:\n"
            "/add <place name> — queue a place\n"
            "/list — show all saved places\n"
            "/list <tag1>, <tag2> — filter by tags (must match all)\n"
            "/delete <place name> — remove a place\n"
            "/help — show this message"
        ),
    )


async def add_command(bot: Bot, chat_id: int, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await bot.send_message(
            chat_id=chat_id,
            text="Please provide a place name. Example: /add Eiffel Tower",
        )
        return
    name = parts[1].strip()
    try:
        db.queue_place(name)
        await bot.send_message(
            chat_id=chat_id,
            text=f"✅ {name} added to your queue! It will be enriched and saved shortly.",
        )
    except Exception:
        traceback.print_exc()
        await bot.send_message(
            chat_id=chat_id,
            text="Failed to save place. Please try again.",
        )


async def list_command(bot: Bot, chat_id: int, text: str):
    parts = text.split(None, 1)
    tags = [t.strip() for t in parts[1].split(",")] if len(parts) > 1 and parts[1].strip() else []

    try:
        places = db.get_all_places(tags=tags if tags else None)
    except Exception:
        traceback.print_exc()
        await bot.send_message(chat_id=chat_id, text="Failed to retrieve places. Please try again.")
        return

    if not places:
        if tags:
            tag_str = ", ".join(tags)
            await bot.send_message(chat_id=chat_id, text=f"No places found with tags: {tag_str}.")
        else:
            await bot.send_message(chat_id=chat_id, text="You have no saved places yet. Use /add <name> to get started.")
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

        lines = [f"📍 *{name_esc}*"]
        if tags_esc:
            lines.append(f"🏷 {tags_esc}")
        if price_esc:
            lines.append(f"💰 {price_esc}")
        if address_esc:
            lines.append(f"📮 {address_esc}")
        if maps_link:
            lines.append(f"🗺 [Open in Google Maps]({maps_link})")
        lines.append(f"📝 {details_esc}")
        lines.append("────────────────────")
        blocks.append("\n".join(lines))

    for i in range(0, len(blocks), 5):
        chunk = "\n\n".join(blocks[i : i + 5])
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")


async def delete_command(bot: Bot, chat_id: int, text: str):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await bot.send_message(
            chat_id=chat_id,
            text="Please provide a place name. Example: /delete Eiffel Tower",
        )
        return
    name = parts[1].strip()
    try:
        deleted = db.delete_place(name)
        await bot.send_message(
            chat_id=chat_id,
            text="Deleted!" if deleted else "Place not found.",
        )
    except Exception:
        traceback.print_exc()
        await bot.send_message(chat_id=chat_id, text="Failed to delete place. Please try again.")


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

        if text.startswith("/start") or text.startswith("/help"):
            await start_command(bot, chat_id)
        elif text.startswith("/add"):
            await add_command(bot, chat_id, text)
        elif text.startswith("/list"):
            await list_command(bot, chat_id, text)
        elif text.startswith("/delete"):
            await delete_command(bot, chat_id, text)


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
        asyncio.run(handle_update(data))
    except Exception:
        traceback.print_exc()
    return "ok", 200
