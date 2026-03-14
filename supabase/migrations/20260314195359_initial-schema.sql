-- ============================================================================
-- Poketeer Supabase Migration
-- Run this in the Supabase SQL Editor (Dashboard > SQL Editor > New Query)
-- ============================================================================

-- 1. Enable required extensions
create extension if not exists vector;        -- pgvector for embedding search
create extension if not exists pg_trgm;       -- trigram fuzzy text search

-- ============================================================================
-- 2. Tables
-- ============================================================================

-- Sets (English + international)
create table sets (
  id          text primary key,
  name        text not null,
  series      text not null default '',
  printed_total int not null default 0,
  total       int not null default 0,
  release_date text not null default '',
  language    text not null default 'en',
  symbol_url  text not null default '',
  logo_url    text not null default ''
);

-- Cards catalog
create table cards (
  id          text primary key,
  name        text not null,
  number      text not null default '',
  set_id      text not null references sets(id),
  rarity      text not null default '',
  image_small text not null default '',
  image_large text not null default '',
  supertype   text not null default '',
  subtypes    text[] not null default '{}',
  hp          text not null default '',
  artist      text not null default '',
  types       text[] not null default '{}'
);

-- Visual embeddings (MobileNetV3 576-D for on-device, or CardEmbedder 512-D)
-- Using 576 to match the ONNX model output; adjust if you use a different model
create table card_embeddings (
  card_id   text primary key references cards(id) on delete cascade,
  embedding vector(576)
);

-- User collections (replaces localStorage)
create table collections (
  user_id    uuid not null references auth.users(id) on delete cascade,
  card_id    text not null references cards(id),
  quantity   int not null default 1,
  price_paid numeric,
  condition  text not null default 'Near Mint',
  notes      text,
  date_added timestamptz not null default now(),
  primary key (user_id, card_id)
);

-- Wishlist
create table wishlist (
  user_id      uuid not null references auth.users(id) on delete cascade,
  card_id      text not null references cards(id),
  target_price numeric,
  priority     text not null default 'Medium',
  date_added   timestamptz not null default now(),
  primary key (user_id, card_id)
);

-- Shared prices cache (one row per card, shared across all users)
create table prices_cache (
  card_id      text primary key references cards(id),
  market_price numeric,
  updated_at   timestamptz not null default now(),
  failed       boolean not null default false
);

-- ============================================================================
-- 3. Indexes
-- ============================================================================

-- Card lookups
create index idx_cards_set_id on cards(set_id);
create index idx_cards_name_trgm on cards using gin(name gin_trgm_ops);
create index idx_cards_number on cards(number);

-- Vector similarity — use HNSW (works on empty tables, no training step)
create index idx_embeddings_cosine
  on card_embeddings
  using hnsw(embedding vector_cosine_ops);

-- Collection / wishlist by user
create index idx_collections_user on collections(user_id);
create index idx_wishlist_user on wishlist(user_id);

-- Prices staleness check
create index idx_prices_updated on prices_cache(updated_at);

-- ============================================================================
-- 4. Row-Level Security (RLS)
-- ============================================================================

-- Public read for cards, sets, embeddings, prices
alter table sets enable row level security;
alter table cards enable row level security;
alter table card_embeddings enable row level security;
alter table prices_cache enable row level security;

create policy "Anyone can read sets"
  on sets for select using (true);

create policy "Anyone can read cards"
  on cards for select using (true);

create policy "Anyone can read embeddings"
  on card_embeddings for select using (true);

create policy "Anyone can read prices"
  on prices_cache for select using (true);

-- Collections: users can only access their own rows
alter table collections enable row level security;

create policy "Users read own collection"
  on collections for select using (auth.uid() = user_id);

create policy "Users insert own collection"
  on collections for insert with check (auth.uid() = user_id);

create policy "Users update own collection"
  on collections for update using (auth.uid() = user_id);

create policy "Users delete own collection"
  on collections for delete using (auth.uid() = user_id);

-- Wishlist: same pattern
alter table wishlist enable row level security;

create policy "Users read own wishlist"
  on wishlist for select using (auth.uid() = user_id);

create policy "Users insert own wishlist"
  on wishlist for insert with check (auth.uid() = user_id);

create policy "Users update own wishlist"
  on wishlist for update using (auth.uid() = user_id);

create policy "Users delete own wishlist"
  on wishlist for delete using (auth.uid() = user_id);

-- ============================================================================
-- 5. RPC Functions
-- ============================================================================

-- Vector similarity search: find the closest cards to a query embedding
create or replace function match_card(
  query_embedding vector(576),
  match_count int default 5
)
returns table(
  id text,
  name text,
  number text,
  set_id text,
  rarity text,
  image_small text,
  image_large text,
  supertype text,
  subtypes text[],
  hp text,
  artist text,
  similarity float
)
language sql stable
as $$
  select
    c.id, c.name, c.number, c.set_id,
    c.rarity, c.image_small, c.image_large,
    c.supertype, c.subtypes, c.hp, c.artist,
    1 - (e.embedding <=> query_embedding) as similarity
  from card_embeddings e
  join cards c on c.id = e.card_id
  order by e.embedding <=> query_embedding
  limit match_count;
$$;

-- Fuzzy card name search using trigram similarity
create or replace function search_cards_fuzzy(
  query text,
  result_limit int default 30,
  result_offset int default 0
)
returns table(
  id text,
  name text,
  number text,
  set_id text,
  rarity text,
  image_small text,
  image_large text,
  supertype text,
  subtypes text[],
  hp text,
  artist text,
  types text[],
  similarity float
)
language sql stable
as $$
  select
    c.id, c.name, c.number, c.set_id,
    c.rarity, c.image_small, c.image_large,
    c.supertype, c.subtypes, c.hp, c.artist, c.types,
    similarity(c.name, query) as similarity
  from cards c
  where c.name % query or c.name ilike '%' || query || '%'
  order by similarity(c.name, query) desc, c.name
  limit result_limit
  offset result_offset;
$$;
