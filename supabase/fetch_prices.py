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


def get_known_card_ids() -> set[str]:
    """Fetch every card id we have locally so we can skip FK violations."""
    print("Fetching known card IDs from Supabase...")
    ids: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        res = (
            sb.table("cards")
            .select("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not res.data:
            break
        ids.update(row["id"] for row in res.data)
        if len(res.data) < page_size:
            break
        offset += page_size
    print(f"  Found {len(ids)} cards")
    return ids


def fetch_prices_for_set(set_id: str) -> dict[str, dict]:
    """Fetch all card prices for a set from pokemontcg.io.

    Returns a dict keyed by card_id with {market, low, high, url}.
    `market` is the first available variant's market price. `low`/`high` are
    the min/max across every numeric field we can see (market, low, mid,
    high, directLow) across every variant, giving an honest "what can this
    sell for" band. `url` is the TCGPlayer listing page.
    """
    headers = {}
    if TCG_API_KEY:
        headers["X-Api-Key"] = TCG_API_KEY

    out: dict[str, dict] = {}
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
                    return out

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
            # Prefer the most common variants; fall back to *any* variant
            # that has a market price so we don't leave cards as null just
            # because they only print as e.g. unlimitedHolofoil / firstEdition.
            PREFERRED = ("holofoil", "normal", "reverseHolofoil", "1stEditionHolofoil")
            market = None
            for v in PREFERRED:
                m = (p.get(v) or {}).get("market")
                if isinstance(m, (int, float)) and m > 0:
                    market = float(m)
                    break
            if market is None:
                for variant_prices in p.values():
                    if not isinstance(variant_prices, dict):
                        continue
                    m = variant_prices.get("market")
                    if isinstance(m, (int, float)) and m > 0:
                        market = float(m)
                        break

            all_values: list[float] = []
            for variant_prices in p.values():
                if not isinstance(variant_prices, dict):
                    continue
                for k in ("low", "mid", "high", "market", "directLow"):
                    v = variant_prices.get(k)
                    if isinstance(v, (int, float)) and v > 0:
                        all_values.append(float(v))

            low = min(all_values) if all_values else None
            high = max(all_values) if all_values else None

            out[card_id] = {
                "market": market,
                "low": low,
                "high": high,
                "url": tcg.get("url"),
            }

        if len(cards) < page_size:
            break
        page += 1

    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Fetching Pokemon TCG prices")
    print("=" * 60)

    start = time.time()

    set_ids = get_set_ids()
    known_card_ids = get_known_card_ids()
    print(f"\nFetching prices for {len(set_ids)} sets...\n")

    all_rows: list[dict] = []
    priced = 0
    skipped_unknown = 0

    for i, set_id in enumerate(set_ids):
        print(f"  [{i+1}/{len(set_ids)}] {set_id}...", end=" ")
        prices = fetch_prices_for_set(set_id)
        count = 0
        skipped = 0
        for card_id, info in prices.items():
            if card_id not in known_card_ids:
                skipped += 1
                continue
            market_price = info.get("market")
            all_rows.append({
                "card_id": card_id,
                "market_price": market_price,
                "low_price": info.get("low"),
                "high_price": info.get("high"),
                "tcgplayer_url": info.get("url"),
                "failed": market_price is None,
            })
            if market_price is not None:
                count += 1
        priced += count
        skipped_unknown += skipped
        suffix = f" ({skipped} unknown)" if skipped else ""
        print(f"{count}/{len(prices) - skipped} priced{suffix}")

        # Small delay to avoid rate limits (no key = ~1000 req/day)
        if not TCG_API_KEY:
            time.sleep(1)

    print(f"\nTotal: {priced} cards with prices, {len(all_rows)} total entries, {skipped_unknown} skipped (not in cards table)")

    if all_rows:
        print("\nUpserting to prices_cache...")
        upsert_batch("prices_cache", all_rows)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
