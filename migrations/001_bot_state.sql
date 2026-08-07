-- Shared persistent state for the Conversation Spark and two-player RPG bots.
create table if not exists public.bot_state (
    id uuid primary key default gen_random_uuid(),
    namespace text not null,
    chat_id bigint not null,
    topic_id bigint not null default 0,
    data jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    unique (namespace, chat_id, topic_id)
);

-- No public policies are created. The bot accesses this table with the
-- server-only SUPABASE_SERVICE_ROLE_KEY, which must never reach a client.
alter table public.bot_state enable row level security;
