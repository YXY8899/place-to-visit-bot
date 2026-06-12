import asyncio
import os
import re
import threading
import traceback

from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler

import db

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if uid.strip().isdigit()
)

flask_app = Flask(__name__)

# Persistent event loop in a daemon thread — bridges PTB async with Flask sync
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

application = (
    Application.builder()
    .token(BOT_TOKEN)
    .updater(None)  # disable polling updater; we feed updates manually
    .build()
)


# ---------------------------------------------------------------------------
# MarkdownV2 helper
# ---------------------------------------------------------------------------

def escape_md(text: str) -> str:
    return re.sub(r'([\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!])', r'\\\1', text)


def is_allowed(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    return update.effective_user.id in ALLOWED_USERS


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_handler(update: Update, context):
    if not is_allowed(update):
        return
    text = (
        "👋 *Place to Visit Bot*\n\n"
        "Save places and restaurants you want to visit\.\n\n"
        "*Commands:*\n"
        "/add \<place name\> — queue a place for enrichment\n"
        "/list — show all saved places\n"
        "/delete \<place name\> — remove a saved place\n"
        "/help — show this message"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def help_handler(update: Update, context):
    await start_handler(update, context)


async def add_handler(update: Update, context):
    if not is_allowed(update):
        return
    try:
        if not context.args:
            await update.message.reply_text(
                "Please provide a place name. Example: /add Eiffel Tower"
            )
            return

        name = " ".join(context.args)
        db.queue_place(name)
        safe_name = escape_md(name)
        await update.message.reply_text(
            f"✅ *{safe_name}* added to your queue\\!\n"
            "It will be enriched with details and saved shortly\\.",
            parse_mode="MarkdownV2",
        )
    except Exception:
        await update.message.reply_text("Failed to save place. Please try again.")


async def list_handler(update: Update, context):
    if not is_allowed(update):
        return
    try:
        places = db.get_all_places()
        if not places:
            await update.message.reply_text(
                "You have no saved places yet. Use /add <name> to get started."
            )
            return

        blocks = []
        for place in places:
            name_esc = escape_md(place["name"]) if place["name"] else "Unknown"
            details_esc = escape_md(place["details"]) if place["details"] else "No details available\\."
            maps_link = place["maps_link"]

            if maps_link:
                block = (
                    f"📍 *{name_esc}*\n"
                    f"🗺 [Open in Google Maps]({maps_link})\n"
                    f"📝 {details_esc}\n"
                    f"────────────────────"
                )
            else:
                block = (
                    f"📍 *{name_esc}*\n"
                    f"📝 {details_esc}\n"
                    f"────────────────────"
                )
            blocks.append(block)

        # Send in groups of 5 to stay under Telegram message length limits
        for i in range(0, len(blocks), 5):
            chunk = blocks[i : i + 5]
            await update.message.reply_text(
                "\n\n".join(chunk), parse_mode="MarkdownV2"
            )
    except Exception:
        await update.message.reply_text(
            "Failed to retrieve places. Please try again."
        )


async def delete_handler(update: Update, context):
    if not is_allowed(update):
        return
    try:
        if not context.args:
            await update.message.reply_text(
                "Please provide a place name. Example: /delete Eiffel Tower"
            )
            return

        name = " ".join(context.args)
        deleted = db.delete_place(name)
        if deleted:
            await update.message.reply_text("Deleted!")
        else:
            await update.message.reply_text("Place not found.")
    except Exception:
        await update.message.reply_text("Failed to delete place. Please try again.")


# ---------------------------------------------------------------------------
# Register handlers
# ---------------------------------------------------------------------------

application.add_handler(CommandHandler("start", start_handler))
application.add_handler(CommandHandler("help", help_handler))
application.add_handler(CommandHandler("add", add_handler))
application.add_handler(CommandHandler("list", list_handler))
application.add_handler(CommandHandler("delete", delete_handler))


# ---------------------------------------------------------------------------
# Startup: initialize PTB, set webhook, ensure sheet headers
# ---------------------------------------------------------------------------

async def _set_webhook():
    await application.bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
    )


asyncio.run_coroutine_threadsafe(application.initialize(), _loop).result()
asyncio.run_coroutine_threadsafe(_set_webhook(), _loop).result()


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
        print(f"Incoming update: {data}", flush=True)
        update = Update.de_json(data, application.bot)
        asyncio.run_coroutine_threadsafe(
            application.process_update(update), _loop
        ).result(timeout=25)
    except Exception as e:
        print(f"Webhook error: {e}", flush=True)
        traceback.print_exc()
    return "ok", 200
