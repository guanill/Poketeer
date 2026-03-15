"""
fetch_prices.py — Fetch market prices from pokemontcg.io and populate prices_cache.

Reads all card IDs from your Supabase `cards` table, fetches TCGPlayer prices
from the Pokemon TCG API, and upserts them into `prices_cache`.

Usage:
    pip install requests supabase python-dotenv
    python supabase/fetch_prices.py

Environment:
    SUPABASE_URL         — project URL
    SUPABASE_SERVICE_KEY — service-role key (NOT the anon key)
    POKEMON_TCG_API_KEY  — (optional) pokemontcg.io API key for higher rate limits
"""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TCG_API_KEY = os.getenv("POKEMON_TCG_API_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.seed")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

API_BASE = "https://api.pokemontcg.io/v2/cards"
BATCH = 500

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def upsert_batch(table: str, rows: list[dict], batch_size: int = BATCH):
    total = len(rows)
    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        sb.table(table).upsert(batch).execute()
        done = min(i + batch_size, total)
        print(f"  {table}: {done}/{total}", end="\r")
    print(f"  {table}: {total}/{total} done")



def get_set_ids() -> list[str]:
    """Fetch English set IDs from Supabase sets table."""
    print("Fetching set IDs from Supabase...")
    all_ids: list[str] = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            sb.table("sets")
            .select("id")
            .eq("language", "en")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not res.data:
            break
        all_ids.extend(row["id"] for row in res.data)
        if len(res.data) < page_size:
            break
        offset += page_size
    print(f"  Found {len(all_ids)} English sets")
    return sorted(all_ids)


def fetch_prices_for_set(set_id: str) -> dict[str, float | None]:
    """Fetch all card prices for a set from pokemontcg.io."""
    headers = {}
    if TCG_API_KEY:
        headers["X-Api-Key"] = TCG_API_KEY

    prices: dict[str, float | None] = {}
    page = 1
    page_size = 250

    while True:
        for attempt in range(3):
            try:
                resp = requests.get(
                    API_BASE,
                    params={
                        "q": f"set.id:{set_id}",
                        "select": "id,tcgplayer",
                        "page": page,
                        "pageSize": page_size,
                    },
                    headers=headers,
                    timeout=30,
                )
                break
            except requests.exceptions.RequestException:
                if attempt < 2:
                    time.sleep(5)
                else:
                    return prices

        if resp.status_code == 429:
            print("    Rate limited, waiting 60s...")
            time.sleep(60)
            continue

        if resp.status_code != 200:
            print(f"    API error {resp.status_code} for set {set_id}, skipping")
            break

        data = resp.json()
        cards = data.get("data", [])

        for card in cards:
            card_id = card["id"]
            tcg = card.get("tcgplayer", {})
            p = tcg.get("prices", {})
            market = (
                (p.get("holofoil") or {}).get("market")
                or (p.get("normal") or {}).get("market")
                or (p.get("reverseHolofoil") or {}).get("market")
                or (p.get("1stEditionHolofoil") or {}).get("market")
            )
            prices[card_id] = market

        if len(cards) < page_size:
            break
        page += 1

    return prices


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Fetching Pokemon TCG prices")
    print("=" * 60)

    start = time.time()

    set_ids = get_set_ids()
    print(f"\nFetching prices for {len(set_ids)} sets...\n")

    all_rows: list[dict] = []
    priced = 0

    for i, set_id in enumerate(set_ids):
        print(f"  [{i+1}/{len(set_ids)}] {set_id}...", end=" ")
        prices = fetch_prices_for_set(set_id)
        count = 0
        for card_id, market_price in prices.items():
            all_rows.append({
                "card_id": card_id,
                "market_price": market_price,
                "failed": market_price is None,
            })
            if market_price is not None:
                count += 1
        priced += count
        print(f"{count}/{len(prices)} priced")

        # Small delay to avoid rate limits (no key = ~1000 req/day)
        if not TCG_API_KEY:
            time.sleep(1)

    print(f"\nTotal: {priced} cards with prices, {len(all_rows)} total entries")

    if all_rows:
        print("\nUpserting to prices_cache...")
        upsert_batch("prices_cache", all_rows)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
