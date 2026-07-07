import math
import os
import re

import httpx
from openai import OpenAI

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")

_MAPS_HEADERS = {"X-Goog-Maps-Solution-ID": "gmp_git_agentskills_v1"}

_nim: OpenAI | None = None


def _get_nim() -> OpenAI:
    global _nim
    if _nim is None:
        _nim = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_NIM_API_KEY,
        )
    return _nim


def _parse_location(raw: str) -> str:
    response = _get_nim().chat.completions.create(
        model="minimaxai/minimax-m3",
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


_SG_SUFFIX_RE = re.compile(r",?\s*Singapore\s*$", re.IGNORECASE)


def _onemap_search(query: str):
    resp = httpx.get(
        "https://www.onemap.gov.sg/api/common/elastic/search",
        params={"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("results"):
        return None
    top = data["results"][0]
    return float(top["LATITUDE"]), float(top["LONGITUDE"])


def _geocode(location: str) -> tuple[float, float] | None:
    # Google's Geocoding API rejects server-side calls on the demo key
    # (REQUEST_DENIED, billing not enabled). Use Singapore's OneMap API
    # instead — free, no key, and handles local landmarks/addresses well.
    # OneMap's index is Singapore-only and its matcher chokes on a trailing
    # ", Singapore" (which the NIM location parser always appends), so strip
    # it before searching, falling back to the untouched string.
    stripped = _SG_SUFFIX_RE.sub("", location).strip()
    return _onemap_search(stripped) or _onemap_search(location)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _format_duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''} {minutes} min{'s' if minutes != 1 else ''}"
    return f"{minutes} min{'s' if minutes != 1 else ''}"


def _transit_duration_seconds(origin_lat, origin_lng, dest_lat, dest_lng) -> int | None:
    # The Maps Demo Key covers the single-route Routes API (computeRoutes)
    # but not the batch computeRouteMatrix, which requires billing even on
    # the demo key. So transit time is looked up one destination at a time.
    resp = httpx.post(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "routes.duration",
            **_MAPS_HEADERS,
        },
        json={
            "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
            "travelMode": "TRANSIT",
        },
        timeout=15,
    )
    resp.raise_for_status()
    routes = resp.json().get("routes")
    if not routes:
        return None
    return int(routes[0]["duration"].rstrip("s").split(".")[0])


def find_nearby(
    raw_location: str, places: list[dict], top_n: int = 3, prefilter_n: int = 6
) -> tuple[str, list[dict]]:
    """
    Returns (parsed_location, top_n places sorted by public transit travel time).
    Places without lat/lng are skipped. Candidates are first narrowed to the
    `prefilter_n` nearest by straight-line distance, then ranked by actual
    transit time (one computeRoutes call per candidate).
    """
    candidates = [p for p in places if p.get("lat") is not None and p.get("lng") is not None]
    if not candidates:
        return raw_location, []

    # Normalise location via LLM, then geocode
    parsed = _parse_location(raw_location)
    coords = _geocode(parsed) or _geocode(raw_location + ", Singapore")
    if not coords:
        return parsed, []

    origin_lat, origin_lng = coords
    candidates.sort(key=lambda p: _haversine_km(origin_lat, origin_lng, p["lat"], p["lng"]))
    candidates = candidates[:prefilter_n]

    results = []
    for place in candidates:
        try:
            seconds = _transit_duration_seconds(origin_lat, origin_lng, place["lat"], place["lng"])
        except httpx.HTTPStatusError:
            continue
        if seconds is None:
            continue
        results.append({
            **place,
            "duration_seconds": seconds,
            "duration_text": _format_duration(seconds),
        })

    results.sort(key=lambda x: x["duration_seconds"])
    return parsed, results[:top_n]
