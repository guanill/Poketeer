-- Change embedding dimension from 576 to 512 to match the CardEmbedder model
-- (ResNet50 + projection head, trained with triplet loss)

-- Drop the old index and column, recreate with correct dimension
drop index if exists idx_embeddings_cosine;
alter table card_embeddings drop column if exists embedding;
alter table card_embeddings add column embedding vector(512);

-- Recreate HNSW index
create index idx_embeddings_cosine
  on card_embeddings
  using hnsw(embedding vector_cosine_ops);

-- Update the match_card RPC to use 512-D
create or replace function match_card(
  query_embedding vector(512),
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
