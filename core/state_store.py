import os
from datetime import datetime, timezone
from typing import Any

import httpx


SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "SUPABASE_KEY", ""
)


def _headers_for(api_key: str) -> dict[str, str]:
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
    }
    # Supabase's newer sb_secret keys must be sent only as apikey. Legacy JWT
    # service_role keys also need Authorization for PostgREST compatibility.
    if not api_key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


_HEADERS = _headers_for(SUPABASE_KEY)


def _url() -> str:
    return f"{SUPABASE_URL}/rest/v1/bot_state"


def load_state(namespace: str, chat_id: int, topic_id: int | None) -> dict[str, Any] | None:
    normalized_topic_id = topic_id or 0
    params = {
        "select": "data",
        "namespace": f"eq.{namespace}",
        "chat_id": f"eq.{chat_id}",
        "topic_id": f"eq.{normalized_topic_id}",
        "limit": "1",
    }
    response = httpx.get(_url(), headers=_HEADERS, params=params, timeout=10)
    response.raise_for_status()
    rows = response.json()
    return rows[0]["data"] if rows else None


def save_state(
    namespace: str,
    chat_id: int,
    topic_id: int | None,
    data: dict[str, Any],
) -> None:
    normalized_topic_id = topic_id or 0
    headers = {
        **_HEADERS,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    response = httpx.post(
        _url(),
        headers=headers,
        params={"on_conflict": "namespace,chat_id,topic_id"},
        json={
            "namespace": namespace,
            "chat_id": chat_id,
            "topic_id": normalized_topic_id,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        timeout=10,
    )
    response.raise_for_status()


def clear_state(namespace: str, chat_id: int, topic_id: int | None) -> None:
    normalized_topic_id = topic_id or 0
    params = {
        "namespace": f"eq.{namespace}",
        "chat_id": f"eq.{chat_id}",
        "topic_id": f"eq.{normalized_topic_id}",
    }
    response = httpx.delete(_url(), headers=_HEADERS, params=params, timeout=10)
    response.raise_for_status()
