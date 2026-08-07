import traceback

from telegram import Bot, Message

import db
import nearby as nearby_service
from core.telegram import escape_markdown, parse_command, reply


HELP_TEXT = (
    "👋 Place to Visit Bot\n\n"
    "Save places and restaurants you want to visit.\n\n"
    "Commands:\n"
    "/add <place name> — queue a place\n"
    "/list — show all saved places\n"
    "/list <tag1>, <tag2> — filter by tags (must match all)\n"
    "/detail <place name> — show full details of a place\n"
    "/nearby <location> — top 3 places by public transit time\n"
    "/visited <place name> — mark a place as visited\n"
    "/tags — show all available tags\n"
    "/pending — show places waiting to be enriched\n"
    "/delete <place name> — remove a place\n"
    "/whereami — show this chat and topic IDs\n"
    "/help — show this message"
)


async def help_command(bot: Bot, message: Message, _arguments: str):
    await reply(bot, message, HELP_TEXT)


async def whereami_command(bot: Bot, message: Message, _arguments: str):
    topic = message.message_thread_id
    await reply(
        bot,
        message,
        f"Chat ID: {message.chat_id}\nTopic ID: {topic if topic is not None else 'General'}",
    )


async def add_command(bot: Bot, message: Message, arguments: str):
    if not arguments:
        await reply(bot, message, "Please provide a place name. Example: /add Eiffel Tower")
        return
    try:
        db.queue_place(arguments)
        await reply(
            bot,
            message,
            f"✅ {arguments} added to your queue! It will be enriched and saved shortly.",
        )
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to save place. Please try again.")


async def list_command(bot: Bot, message: Message, arguments: str):
    tags = [tag.strip() for tag in arguments.split(",") if tag.strip()]
    try:
        places = db.get_all_places(tags=tags or None)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to retrieve places. Please try again.")
        return

    if not places:
        if tags:
            await reply(bot, message, f"No places found with tags: {', '.join(tags)}.")
        else:
            await reply(bot, message, "You have no saved places yet. Use /add <name> to get started.")
        return

    blocks = []
    for place in places:
        name = escape_markdown(place.get("name") or "Unknown")
        maps_link = place.get("maps_link") or ""
        address = escape_markdown(place.get("address") or "")
        price = escape_markdown(place.get("price_range") or "")
        tags_text = escape_markdown(", ".join(place.get("tags") or []))

        lines = [f"📍 *{name}*"]
        if tags_text:
            lines.append(f"🏷 {tags_text}")
        if price:
            lines.append(f"💰 {price}")
        if address:
            lines.append(f"📮 {address}")
        if maps_link:
            lines.append(f"🗺 [Open in Google Maps]({maps_link})")
        lines.append("────────────────────")
        blocks.append("\n".join(lines))

    for index in range(0, len(blocks), 5):
        await reply(
            bot,
            message,
            "\n\n".join(blocks[index : index + 5]),
            parse_mode="MarkdownV2",
        )


async def detail_command(bot: Bot, message: Message, arguments: str):
    if not arguments:
        await reply(bot, message, "Please provide a place name. Example: /detail Lau Pa Sat")
        return
    try:
        place = db.get_place(arguments)
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to retrieve place. Please try again.")
        return

    if not place:
        await reply(bot, message, f'No place found matching "{arguments}".')
        return

    name = escape_markdown(place.get("name") or arguments)
    details = escape_markdown(place.get("details") or "No details available.")
    address = escape_markdown(place.get("address") or "")
    price = escape_markdown(place.get("price_range") or "")
    tags_text = escape_markdown(", ".join(place.get("tags") or []))
    maps_link = place.get("maps_link") or ""

    lines = [f"📍 *{name}*"]
    if tags_text:
        lines.append(f"🏷 {tags_text}")
    if price:
        lines.append(f"💰 {price}")
    if address:
        lines.append(f"📮 {address}")
    if maps_link:
        lines.append(f"🗺 [Open in Google Maps]({maps_link})")
    lines.append(f"📝 {details}")
    await reply(bot, message, "\n".join(lines), parse_mode="MarkdownV2")


async def nearby_command(bot: Bot, message: Message, arguments: str):
    if not arguments:
        await reply(bot, message, "Please provide a location. Example: /nearby Bugis MRT")
        return

    await reply(bot, message, "🔍 Finding nearby places via public transport...")
    try:
        parsed_location, results = nearby_service.find_nearby(
            arguments,
            db.get_all_places(),
            top_n=3,
        )
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to find nearby places. Please try again.")
        return

    if not results:
        await reply(
            bot,
            message,
            f"No nearby places found from {arguments}. Places need coordinates to be searchable.",
        )
        return

    blocks = []
    for index, place in enumerate(results, 1):
        name = escape_markdown(place.get("name") or "")
        duration = escape_markdown(place.get("duration_text") or "")
        address = escape_markdown(place.get("address") or "")
        price = escape_markdown(place.get("price_range") or "")
        tags_text = escape_markdown(", ".join(place.get("tags") or []))
        maps_link = place.get("maps_link") or ""

        lines = [f"{index}\\. 📍 *{name}* — 🚌 {duration}"]
        if tags_text:
            lines.append(f"   🏷 {tags_text}")
        if price:
            lines.append(f"   💰 {price}")
        if address:
            lines.append(f"   📮 {address}")
        if maps_link:
            lines.append(f"   🗺 [Open in Google Maps]({maps_link})")
        blocks.append("\n".join(lines))

    header = f"🚌 *Top 3 places from {escape_markdown(parsed_location)}:*\n\n"
    await reply(
        bot,
        message,
        header + "\n\n".join(blocks) + "\n\nGoogle Maps",
        parse_mode="MarkdownV2",
    )


async def pending_command(bot: Bot, message: Message, _arguments: str):
    try:
        pending = db.get_pending()
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to retrieve queue. Please try again.")
        return
    if not pending:
        await reply(bot, message, "No places in the queue.")
        return
    lines = [f"⏳ *{len(pending)} place(s) pending enrichment:*"]
    lines.extend(escape_markdown(f"{index}. {item['name']}") for index, item in enumerate(pending, 1))
    await reply(bot, message, "\n".join(lines), parse_mode="MarkdownV2")


async def tags_command(bot: Bot, message: Message, _arguments: str):
    try:
        tags = db.get_all_tags()
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to retrieve tags. Please try again.")
        return
    if not tags:
        await reply(bot, message, "No tags found. Add some places first.")
        return
    tag_list = "\n".join(f"• {escape_markdown(tag)}" for tag in tags)
    await reply(bot, message, f"🏷 *Available tags:*\n{tag_list}", parse_mode="MarkdownV2")


async def visited_command(bot: Bot, message: Message, arguments: str):
    if not arguments:
        await reply(bot, message, "Please provide a place name. Example: /visited Lau Pa Sat")
        return
    try:
        marked = db.mark_visited(arguments)
        await reply(bot, message, f"✅ {arguments} marked as visited!" if marked else "Place not found.")
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to update place. Please try again.")


async def delete_command(bot: Bot, message: Message, arguments: str):
    if not arguments:
        await reply(bot, message, "Please provide a place name. Example: /delete Eiffel Tower")
        return
    try:
        deleted = db.delete_place(arguments)
        await reply(bot, message, "Deleted!" if deleted else "Place not found.")
    except Exception:
        traceback.print_exc()
        await reply(bot, message, "Failed to delete place. Please try again.")


COMMANDS = {
    "start": help_command,
    "help": help_command,
    "whereami": whereami_command,
    "add": add_command,
    "list": list_command,
    "detail": detail_command,
    "nearby": nearby_command,
    "pending": pending_command,
    "tags": tags_command,
    "visited": visited_command,
    "delete": delete_command,
}


async def handle_message(bot: Bot, message: Message):
    parsed = parse_command(message.text or "")
    if parsed is None:
        return
    command, arguments = parsed
    handler = COMMANDS.get(command)
    if handler:
        await handler(bot, message, arguments)
