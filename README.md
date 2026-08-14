# Couples Telegram Bot Hub

One Render service runs three Telegram bots for the same two-person group:

- **Place to Visit** keeps a shared list of places and ranks nearby options by transit time.
- **Conversation Spark** uses AI to create playful, curious, or deeper questions without making the relationship feel like homework.
- **Two-Player AI RPG** runs a cooperative, turn-based story with an AI game master.

Each bot has its own BotFather token and Telegram topic. They share deployment, access control, Supabase, and webhook infrastructure, but their commands and state remain isolated.

## Architecture

```text
Telegram group
  Places topic       -> Places bot       -> bots/places
  Conversation topic -> Conversation bot -> bots/conversation
  RPG topic          -> RPG bot          -> bots/rpg
                              |
                       core runtime/state
                              |
                  Flask + Supabase + NVIDIA NIM
```

The Render entry point remains `gunicorn --workers 1 bot:flask_app`. At startup, each configured token gets a webhook at `/webhook/<bot-slug>` protected by Telegram's secret-token header. Bots ignore messages outside the configured group, topic, or two-user allowlist.

Python is pinned to 3.12 in `.python-version` so Render does not silently select a newer runtime that is incompatible with the pinned Telegram library.

## Telegram setup

1. Create two additional bots with `@BotFather`, one for Conversation Spark and one for the RPG.
2. Add all three bots to the private Telegram group.
3. Create three topics: Places, Conversation, and RPG.
4. Temporarily leave the relevant `*_TOPIC_ID` unset. Deploy, then run `/whereami@your_bot_username` inside each topic.
5. Copy the returned group ID to `COUPLE_CHAT_ID` and each topic ID to its matching environment variable.
6. Set both partners' numeric user IDs in `ALLOWED_USER_IDS`, separated by a comma, then redeploy.

Bots normally only need permission to read and send messages. If privacy mode prevents commands from reaching a bot, use BotFather's `/setprivacy` setting for that bot; commands explicitly addressed to the bot also work in privacy mode.

## Supabase setup

Run [`migrations/001_bot_state.sql`](migrations/001_bot_state.sql) in the Supabase SQL editor. It creates the JSON state table used by Conversation Spark and the RPG, with row-level security enabled and no public policies. Set the server-only service-role key in Render; never put it in a browser, mobile app, or committed file. The existing `input` and `places` tables remain unchanged.

## Render environment

| Variable | Purpose |
|---|---|
| `WEBHOOK_URL` | Public Render URL without a trailing slash |
| `BOT_TOKEN` | Existing Place bot token; `PLACE_BOT_TOKEN` is also accepted |
| `CONVERSATION_BOT_TOKEN` | Conversation Spark bot token |
| `RPG_BOT_TOKEN` | RPG bot token |
| `COUPLE_CHAT_ID` | Shared Telegram supergroup ID, normally starting with `-100` |
| `PLACE_TOPIC_ID` | Places topic ID |
| `CONVERSATION_TOPIC_ID` | Conversation topic ID |
| `RPG_TOPIC_ID` | RPG topic ID |
| `ALLOWED_USER_IDS` | Exactly the two allowed Telegram user IDs, comma-separated |
| `SUPABASE_URL`, `SUPABASE_KEY` | Existing Supabase REST credentials |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only key for protected `bot_state` access |
| `NVIDIA_NIM_API_KEY` | Used by location parsing and the RPG game master |
| `RPG_NIM_MODEL` | Optional; defaults to `minimaxai/minimax-m3` |
| `GOOGLE_MAPS_API_KEY` | Used by the Place bot's transit-time lookup |

A bot whose token is empty is simply not registered. This lets you deploy the redesign with the Place bot first, then add the other two safely.

## Commands

Conversation Spark:

- `/question` — random prompt
- `/question fun`, `/question curious`, `/question deep` — choose a tone
- `/next` — replace the current prompt

Two-Player AI RPG:

- `/newgame <theme>` — Player 1 creates an adventure
- `/join` — the other partner joins as Player 2
- `/act <action>` — take the current turn
- `/status` — show the scene and whose turn it is
- `/endgame` — clear the active game

Every bot supports `/whereami` and `/help` in its own topic.

## Local checks

```powershell
python -m compileall bot.py core bots
python -m unittest discover -s tests
```
