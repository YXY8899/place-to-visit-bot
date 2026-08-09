import asyncio
import hashlib
import hmac
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Awaitable, Callable

from flask import Flask, abort, jsonify, request
from telegram import Bot, BotCommand, Message, Update


Handler = Callable[[Bot, Message], Awaitable[None]]


@dataclass(frozen=True)
class BotRegistration:
    slug: str
    token: str
    handler: Handler
    topic_id: int | None = None
    commands: tuple[tuple[str, str], ...] = ()

    @property
    def webhook_secret(self) -> str:
        return hashlib.sha256(f"{self.slug}:{self.token}".encode()).hexdigest()


class BotRuntime:
    def __init__(
        self,
        registrations: list[BotRegistration],
        webhook_url: str,
        chat_id: int | None,
        allowed_user_ids: frozenset[int],
    ):
        self.registrations = {
            registration.slug: registration
            for registration in registrations
            if registration.token
        }
        self.webhook_url = webhook_url
        self.chat_id = chat_id
        self.allowed_user_ids = allowed_user_ids
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, len(self.registrations)),
            thread_name_prefix="telegram-update",
        )

    async def handle_update(self, registration: BotRegistration, data: dict):
        async with Bot(token=registration.token) as bot:
            update = Update.de_json(data, bot)
            message = update.message
            if not message or not message.text:
                return

            user_id = message.from_user.id if message.from_user else None
            if self.allowed_user_ids and user_id not in self.allowed_user_ids:
                return
            if self.chat_id is not None and message.chat_id != self.chat_id:
                return
            if (
                registration.topic_id is not None
                and message.message_thread_id != registration.topic_id
            ):
                return

            await registration.handler(bot, message)

    async def register_webhooks(self):
        if not self.webhook_url:
            print("WEBHOOK_URL is not configured; webhook registration skipped.", flush=True)
            return

        for registration in self.registrations.values():
            try:
                async with Bot(token=registration.token) as bot:
                    await bot.set_webhook(
                        url=f"{self.webhook_url}/webhook/{registration.slug}",
                        secret_token=registration.webhook_secret,
                    )
                    if registration.commands:
                        await bot.set_my_commands(
                            [
                                BotCommand(command, description)
                                for command, description in registration.commands
                            ]
                        )
                print(f"Webhook registered for {registration.slug}.", flush=True)
            except Exception:
                print(
                    f"Failed to register webhook for {registration.slug}.", flush=True
                )
                traceback.print_exc()

    def create_flask_app(self) -> Flask:
        app = Flask(__name__)

        @app.get("/")
        def health():
            return jsonify(
                status="ok",
                bots=sorted(self.registrations),
            )

        @app.post("/webhook/<slug>")
        def webhook(slug: str):
            registration = self.registrations.get(slug)
            if registration is None:
                abort(404)

            supplied_secret = request.headers.get(
                "X-Telegram-Bot-Api-Secret-Token", ""
            )
            if not hmac.compare_digest(
                supplied_secret, registration.webhook_secret
            ):
                abort(403)

            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                abort(400)

            self.executor.submit(
                asyncio.run,
                self.handle_update(registration, data),
            )
            return "ok", 200

        return app
