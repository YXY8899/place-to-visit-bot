import os

import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def queue_place(name: str):
    resp = httpx.post(_url("input"), headers=_HEADERS, json={"name": name})
    resp.raise_for_status()


def get_pending() -> list[dict]:
    resp = httpx.get(_url("input"), headers=_HEADERS, params={"select": "id,name"})
    resp.raise_for_status()
    return resp.json()


def append_place(name: str, maps_link: str, details: str):
    resp = httpx.post(
        _url("places"),
        headers=_HEADERS,
        json={"name": name, "maps_link": maps_link, "details": details},
    )
    resp.raise_for_status()


def delete_input_row(row_id: str):
    resp = httpx.delete(
        _url("input"), headers=_HEADERS, params={"id": f"eq.{row_id}"}
    )
    resp.raise_for_status()


def get_all_places(tags: list[str] | None = None) -> list[dict]:
    params = {"select": "name,maps_link,tags,address,price_range", "order": "created_at.asc", "visited": "eq.false"}
    if tags:
        params["tags"] = "cs.{" + ",".join(tags) + "}"
    resp = httpx.get(_url("places"), headers=_HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def get_place(name: str) -> dict | None:
    resp = httpx.get(
        _url("places"),
        headers=_HEADERS,
        params={"select": "name,maps_link,details,tags,address,price_range", "name": f"ilike.{name.strip()}", "limit": "1"},
    )
    resp.raise_for_status()
    results = resp.json()
    return results[0] if results else None


def get_all_tags() -> list[str]:
    resp = httpx.get(_url("places"), headers=_HEADERS, params={"select": "tags", "visited": "eq.false"})
    resp.raise_for_status()
    seen = set()
    for row in resp.json():
        for tag in (row.get("tags") or []):
            seen.add(tag)
    return sorted(seen)


def mark_visited(name: str) -> bool:
    from datetime import datetime, timezone
    resp = httpx.patch(
        _url("places"),
        headers=_HEADERS,
        params={"name": f"ilike.{name.strip()}"},
        json={"visited": True, "visited_at": datetime.now(timezone.utc).isoformat()},
    )
    resp.raise_for_status()
    return len(resp.json()) > 0


def delete_place(name: str) -> bool:
    resp = httpx.delete(
        _url("places"),
        headers=_HEADERS,
        params={"name": f"ilike.{name.strip()}"},
    )
    resp.raise_for_status()
    return len(resp.json()) > 0
