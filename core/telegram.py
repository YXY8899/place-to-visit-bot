import re

from telegram import Bot, Message


def escape_markdown(text: str) -> str:
    return re.sub(r"([\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!])", r"\\\1", text)


def parse_command(text: str) -> tuple[str, str] | None:
    head, _, arguments = text.strip().partition(" ")
    if not head.startswith("/"):
        return None
    command = head[1:].split("@", 1)[0].lower()
    return command, arguments.strip()


async def send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    thread_id: int | None = None,
    **kwargs,
):
    if thread_id is not None:
        kwargs["message_thread_id"] = thread_id
    await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def reply(bot: Bot, message: Message, text: str, **kwargs):
    await send_message(
        bot,
        message.chat_id,
        text,
        message.message_thread_id,
        **kwargs,
    )

