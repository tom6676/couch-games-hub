-- Party Cloud Board — free-tier Supabase schema
-- Run once in Supabase SQL editor.

create table if not exists public.games (
  id bigint generated always as identity primary key,
  slug text not null unique,
  title text not null,
  max_players integer not null default 0,
  genres jsonb not null default '[]'::jsonb,
  platforms jsonb not null default '[]'::jsonb,
  screenshots jsonb not null default '[]'::jsonb, -- array of URL strings
  cover text,
  gfn_status text,          -- BYOG / Unavailable / ...
  game_pass_status text,    -- All-Inclusive / Not listed / ...
  buyer_type text not null default 'unknown'
    check (buyer_type in ('cd_key', 'secondary_account', 'unknown')),
  cpu text,
  gpu text,
  ram_gb integer,
  storage_gb integer,
  store_links jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists games_max_players_idx on public.games (max_players);

alter table public.games enable row level security;

-- Public read for GitHub Pages (anon key)
drop policy if exists "Public read games" on public.games;
create policy "Public read games"
  on public.games for select
  to anon, authenticated
  using (true);

-- Writes only via service role (bypasses RLS) from GitHub Actions
