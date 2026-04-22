-- ============================================================================
-- prices_cache: add TCGPlayer listing URL + low/high price band.
--
-- market_price stays the headline number. low/high capture the cheapest and
-- priciest variant so the UI can show a range. tcgplayer_url is the deep
-- link to the listing page on TCGPlayer for the user to open through to buy.
-- ============================================================================

alter table prices_cache
  add column if not exists tcgplayer_url text,
  add column if not exists low_price     numeric,
  add column if not exists high_price    numeric;
