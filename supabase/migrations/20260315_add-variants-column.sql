-- Add variants column to collections table
-- Tracks which card variants the user owns (normal, holofoil, reverseHolofoil, firstEdition)
alter table collections add column if not exists variants text[] not null default '{}';
