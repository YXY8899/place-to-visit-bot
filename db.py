import os

from supabase import create_client, Client

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
    return _client


def queue_place(name: str):
    _get_client().table("input").insert({"name": name}).execute()


def get_pending() -> list[dict]:
    result = _get_client().table("input").select("id, name").execute()
    return [{"id": row["id"], "name": row["name"]} for row in result.data]


def append_place(name: str, maps_link: str, details: str):
    _get_client().table("places").insert(
        {"name": name, "maps_link": maps_link, "details": details}
    ).execute()


def delete_input_row(row_id: str):
    _get_client().table("input").delete().eq("id", row_id).execute()


def get_all_places() -> list[dict]:
    result = (
        _get_client()
        .table("places")
        .select("name, maps_link, details")
        .order("created_at")
        .execute()
    )
    return result.data


def delete_place(name: str) -> bool:
    result = (
        _get_client()
        .table("places")
        .delete()
        .ilike("name", name.strip())
        .execute()
    )
    return len(result.data) > 0
