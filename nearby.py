import os

import httpx
from openai import OpenAI

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")

_MAPS_HEADERS = {"X-Goog-Maps-Solution-ID": "gmp_git_agentskills_v1"}

_nim = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_NIM_API_KEY,
)


def _parse_location(raw: str) -> str:
    response = _nim.chat.completions.create(
        model="z-ai/glm-5.2",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a location parser for Singapore. "
                    "The user gives a location — it may be informal or abbreviated. "
                    "Return only the clean, geocodable place name or address in Singapore. "
                    "Examples: 'near bugis' → 'Bugis, Singapore', "
                    "'tamp mall' → 'Tampines Mall, Singapore', "
                    "'i am at ps' → 'Plaza Singapura, Singapore'. "
                    "Return nothing else — no explanation, no punctuation."
                ),
            },
            {"role": "user", "content": raw},
        ],
        temperature=0.1,
        max_tokens=64,
        stream=False,
    )
    return response.choices[0].message.content.strip()


def _geocode(location: str) -> tuple[float, float] | None:
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        headers=_MAPS_HEADERS,
        params={"address": location, "key": GOOGLE_MAPS_API_KEY},
    )
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "OK" or not data["results"]:
        return None
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def find_nearby(raw_location: str, places: list[dict], top_n: int = 3) -> tuple[str, list[dict]]:
    """
    Returns (parsed_location, top_n places sorted by public transit travel time).
    Places without an address are skipped.
    """
    places_with_addr = [p for p in places if p.get("address")]
    if not places_with_addr:
        return raw_location, []

    # Normalise location via LLM, then geocode
    parsed = _parse_location(raw_location)
    coords = _geocode(parsed) or _geocode(raw_location + ", Singapore")
    if not coords:
        return parsed, []

    origin = f"{coords[0]},{coords[1]}"
    results = []

    # Distance Matrix API supports up to 25 destinations per request
    for i in range(0, len(places_with_addr), 25):
        batch = places_with_addr[i : i + 25]
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            headers=_MAPS_HEADERS,
            params={
                "origins": origin,
                "destinations": "|".join(p["address"] for p in batch),
                "mode": "transit",
                "key": GOOGLE_MAPS_API_KEY,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != "OK":
            continue

        for place, element in zip(batch, data["rows"][0]["elements"]):
            if element["status"] == "OK":
                results.append({
                    **place,
                    "duration_seconds": element["duration"]["value"],
                    "duration_text": element["duration"]["text"],
                })

    results.sort(key=lambda x: x["duration_seconds"])
    return parsed, results[:top_n]
