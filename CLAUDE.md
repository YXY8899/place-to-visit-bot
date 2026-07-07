# place-to-visit-bot

Telegram bot for 2 users to log places/restaurants to visit (shared list). Users queue names via `/add`; a Claude Routine enriches entries daily and writes to Supabase.

## Stack

- Python 3.14 (Render default)
- `python-telegram-bot==20.7` — webhook mode, `async with Bot(token)` per request
- `Flask==3.0.3` + `gunicorn==21.2.0` — sync WSGI
- `openai>=1.0.0` — NVIDIA NIM client (OpenAI-compatible)
- `httpx` — transitive via PTB, reused for Supabase REST API calls
- No `supabase-py` — incompatible with PTB's `httpx~=0.25.2`

## Deployment

- **Platform:** Render (free tier) — https://place-to-visit-bot.onrender.com
- **Repo:** https://github.com/YXY8899/place-to-visit-bot
- **Start command:** `gunicorn --workers 1 bot:flask_app`
- **Webhook:** registered at startup via `asyncio.run(_set_webhook())`
- **Webhook handler** runs in a background thread — returns 200 to Telegram immediately, processes async in background to avoid gunicorn worker timeouts

## Render Environment Variables

| Key | Notes |
|-----|-------|
| `BOT_TOKEN` | Telegram bot token |
| `WEBHOOK_URL` | `https://place-to-visit-bot.onrender.com` |
| `SUPABASE_URL` | `https://opnznafqhrldesftmvvw.supabase.co` |
| `SUPABASE_KEY` | JWT anon key (208 chars) |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs |
| `GOOGLE_MAPS_API_KEY` | Demo key — server-side Geocoding API not supported, Distance Matrix + transit works |
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM API key |

## Database: Supabase (project: opnznafqhrldesftmvvw)

RLS is **disabled** on both tables — required, do not re-enable.

### `input` table (queue)
| Column | Type |
|--------|------|
| `id` | uuid PK |
| `created_at` | timestamptz |
| `name` | text |

### `places` table (enriched output)
| Column | Type |
|--------|------|
| `id` | uuid PK |
| `created_at` | timestamptz |
| `name` | text |
| `maps_link` | text |
| `details` | text |
| `tags` | text[] |
| `address` | text |
| `price_range` | text (`$` / `$$` / `$$$`) |
| `visited` | boolean DEFAULT false |
| `visited_at` | timestamptz |
| `lat` | double precision |
| `lng` | double precision |

## Bot Commands

| Command | Description |
|---------|-------------|
| `/add <name>` | Queues a place to the `input` table |
| `/list` | Shows all unvisited places (name, tags, price, address, maps link) |
| `/list <tag1>, <tag2>` | Filters by tags — AND logic, comma-separated |
| `/detail <name>` | Full details including description |
| `/nearby <location>` | Top 3 unvisited places by public transit time from given location |
| `/visited <name>` | Marks place as visited — hides from `/list`, stays in DB |
| `/tags` | Lists all tags in use across unvisited places |
| `/pending` | Shows places in `input` queue waiting to be enriched |
| `/delete <name>` | Permanently removes a place |
| `/help` | Shows command list |

## Key Architecture Decisions

**Webhook pattern:** `async with Bot(token=BOT_TOKEN) as bot` inside `asyncio.run()` per request. Background thread returns 200 immediately.

**db.py:** All Supabase calls use httpx REST API directly — no supabase-py.

**nearby.py:** NVIDIA NIM (GLM-5.2) normalises informal location input → Geocoding API gets coordinates → Distance Matrix API (transit mode) calculates travel times to all places with addresses → top 3 returned. NIM client is lazy-initialised to avoid startup crash when env var is missing.

**Google Maps demo key limitation:** Server-side Geocoding API returns REQUEST_DENIED. Use Nominatim (OpenStreetMap) for server-side geocoding. Distance Matrix API with transit mode works fine with the demo key.

## Claude Enrichment Routine

- **Where:** `claude.ai/code/routines`
- **Schedule:** Daily 0700 SGT (2300 UTC)
- **Connector:** Supabase MCP (add at `claude.ai/customize/connectors`)
- **Prompt:** See `routine_prompt.md`
- **Routine env vars:** `BOT_TOKEN`, `CHAT_IDS` (comma-separated)

### Hardcoded Tag System

**Category tags:** `Restaurant`, `Café`, `Hawker`, `Bar`, `Bakery`, `Dessert`, `Fine Dining`, `Fast Food`, `Attraction`, `Nature`, `Shopping`, `Activities`, `Others`

**Cuisine tags** (required for food places): `Chinese`, `Japanese`, `Korean`, `Italian`, `Western`, `Indian`, `Malay`, `Thai`, `Vietnamese`, `Mexican`, `Mediterranean`, `French`, `American`, `Middle Eastern`, `Peranakan`, `Seafood`, `Vegetarian`, `Fusion`, `Local`

## Local Dev Notes

- Credentials stored in `.env` and `credentials.json` (both gitignored)
- No `.venv` in project — use system Python (`python` command)
- `httpx` available globally as PTB transitive dep
- Google Maps agent skills installed at `.agents/skills/google-maps-platform/`

## Known Issues / Gotchas

- Google Maps demo key does NOT support server-side Geocoding API (REQUEST_DENIED) — use Nominatim for geocoding
- Nominatim rate limit: 1 request/second, requires `User-Agent` header
- supabase-py incompatible with httpx 0.25.2 — never add it back
- MarkdownV2: always escape with `escape_md()`, never use raw special chars
- `/nearby` is slow (NIM + Maps API) — background thread prevents timeout
- `lat`/`lng` backfill incomplete — Nominatim couldn't find ~13 places; these are skipped in `/nearby` distance pre-filter
