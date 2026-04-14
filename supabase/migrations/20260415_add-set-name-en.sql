-- Add name_en column to sets table for English set names
ALTER TABLE sets ADD COLUMN IF NOT EXISTS name_en text not null default '';
