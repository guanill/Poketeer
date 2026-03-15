-- Drop foreign key constraints on collections and wishlist card_id columns.
-- The collection/wishlist stores card IDs from the Pokemon TCG API, which may
-- not exist in the local cards catalog table. The FK constraint causes silent
-- insert failures when syncing user collections to Supabase.

alter table collections drop constraint if exists collections_card_id_fkey;
alter table wishlist drop constraint if exists wishlist_card_id_fkey;
