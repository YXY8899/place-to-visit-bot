import os


def optional_int_env(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    return int(value) if value else None


def user_id_allowlist() -> frozenset[int]:
    return frozenset(
        int(value.strip())
        for value in os.environ.get("ALLOWED_USER_IDS", "").split(",")
        if value.strip().isdigit()
    )


WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
COUPLE_CHAT_ID = optional_int_env("COUPLE_CHAT_ID") or optional_int_env(
    "PLACE_CHAT_ID"
)
ALLOWED_USER_IDS = user_id_allowlist()

PLACE_BOT_TOKEN = os.environ.get("PLACE_BOT_TOKEN") or os.environ.get(
    "BOT_TOKEN", ""
)
PLACE_TOPIC_ID = optional_int_env("PLACE_TOPIC_ID")

CONVERSATION_BOT_TOKEN = os.environ.get("CONVERSATION_BOT_TOKEN", "")
CONVERSATION_TOPIC_ID = optional_int_env("CONVERSATION_TOPIC_ID")

RPG_BOT_TOKEN = os.environ.get("RPG_BOT_TOKEN", "")
RPG_TOPIC_ID = optional_int_env("RPG_TOPIC_ID")

