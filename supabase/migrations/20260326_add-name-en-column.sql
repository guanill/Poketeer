-- Add name_en column to cards table for storing English/Latin names
-- This is primarily used for Japanese cards so users can see the romanized name
ALTER TABLE cards ADD COLUMN IF NOT EXISTS name_en text not null default '';

-- Index for searching by English name
CREATE INDEX IF NOT EXISTS idx_cards_name_en_trgm ON cards USING gin(name_en gin_trgm_ops);

-- Update fuzzy search to also match against name_en
CREATE OR REPLACE FUNCTION search_cards_fuzzy(
  query text,
  result_limit int default 30,
  result_offset int default 0
)
RETURNS TABLE(
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
LANGUAGE sql STABLE
AS $$
  SELECT
    c.id, c.name, c.number, c.set_id,
    c.rarity, c.image_small, c.image_large,
    c.supertype, c.subtypes, c.hp, c.artist, c.types,
    GREATEST(similarity(c.name, query), similarity(c.name_en, query)) AS similarity
  FROM cards c
  WHERE c.name % query
     OR c.name ILIKE '%' || query || '%'
     OR (c.name_en <> '' AND (c.name_en % query OR c.name_en ILIKE '%' || query || '%'))
  ORDER BY GREATEST(similarity(c.name, query), similarity(c.name_en, query)) DESC, c.name
  LIMIT result_limit
  OFFSET result_offset;
$$;
