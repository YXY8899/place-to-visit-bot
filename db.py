import os

import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

print(f"[db] SUPABASE_URL set: {bool(SUPABASE_URL)}, SUPABASE_KEY length: {len(SUPABASE_KEY)}", flush=True)

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
    if not resp.is_success:
        print(f"[db] queue_place error {resp.status_code}: {resp.text}", flush=True)
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


def get_all_places() -> list[dict]:
    resp = httpx.get(
        _url("places"),
        headers=_HEADERS,
        params={"select": "name,maps_link,details", "order": "created_at.asc"},
    )
    resp.raise_for_status()
    return resp.json()


def delete_place(name: str) -> bool:
    resp = httpx.delete(
        _url("places"),
        headers=_HEADERS,
        params={"name": f"ilike.{name.strip()}"},
    )
    resp.raise_for_status()
    return len(resp.json()) > 0
