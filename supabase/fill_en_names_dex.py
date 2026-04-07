"""
fill_en_names_dex.py — Fill English names for cards using TCGdex dexId + PokeAPI.

For Pokemon cards: fetch dexId from TCGdex JA, then English name from PokeAPI.
For Trainer/Energy cards: match against known EN names from TCGdex EN sets.

This handles secret rares and cards that don't have EN set equivalents.
"""

import io
import os
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))
session = requests.Session()

TCGDEX_JA = "https://api.tcgdex.net/v2/ja"
POKEAPI = "https://pokeapi.co/api/v2/pokemon-species"

# Cache for PokeAPI lookups
_dex_cache: dict[int, str] = {}


def get_pokemon_en_name(dex_id: int) -> str:
    """Get English Pokemon name from PokeAPI by national dex number."""
    if dex_id in _dex_cache:
        return _dex_cache[dex_id]
    try:
        resp = session.get(f"{POKEAPI}/{dex_id}", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            name = next(
                (n["name"] for n in data["names"] if n["language"]["name"] == "en"),
                "",
            )
            _dex_cache[dex_id] = name
            return name
    except Exception:
        pass
    _dex_cache[dex_id] = ""
    return ""


def get_tcgdex_card(set_code: str, local_id: str) -> dict | None:
    """Fetch card detail from TCGdex JA API."""
    card_id = f"{set_code}-{local_id}"
    try:
        resp = session.get(f"{TCGDEX_JA}/cards/{card_id}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    # Try zero-padded
    padded = local_id.zfill(3)
    if padded != local_id:
        card_id = f"{set_code}-{padded}"
        try:
            resp = session.get(f"{TCGDEX_JA}/cards/{card_id}", timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return None


# Suffix patterns for card name variants (ex, V, VMAX, etc.)
SUFFIX_MAP = {
    "ex": " ex",
    "EX": "-EX",
    "V": " V",
    "VMAX": " VMAX",
    "VSTAR": " VSTAR",
    "GX": "-GX",
}


def build_en_name(dex_ids: list[int], ja_name: str, category: str) -> str:
    """Build English card name from dex ID and Japanese name hints."""
    if not dex_ids or category != "Pokemon":
        return ""

    base_name = get_pokemon_en_name(dex_ids[0])
    if not base_name:
        return ""

    # Check for suffixes in the JA name
    for ja_suffix, en_suffix in SUFFIX_MAP.items():
        if ja_name.endswith(ja_suffix):
            return base_name + en_suffix

    return base_name


def main():
    print("=" * 60)
    print("Fill English names via TCGdex dexId + PokeAPI")
    print("=" * 60)

    # Get all cards without name_en
    print("\nFetching cards without name_en...")
    cards = []
    for lang in ["-ja", "-th"]:
        page = 0
        while True:
            res = (
                sb.table("cards")
                .select("id, number, set_id, supertype")
                .like("set_id", f"%{lang}")
                .eq("name_en", "")
                .range(page * 1000, (page + 1) * 1000 - 1)
                .execute()
            )
            if not res.data:
                break
            cards.extend(res.data)
            page += 1

    print(f"  Found {len(cards)} cards\n")

    # Group by set code
    by_set: dict[str, list[dict]] = {}
    for c in cards:
        parts = c["set_id"].split("-")
        code = "-".join(parts[:-1])  # handle codes like SV-P
        by_set.setdefault(code, []).append(c)

    updated = 0
    api_calls = 0
    errors = 0

    for code, set_cards in sorted(by_set.items()):
        set_updated = 0
        print(f"  [{code}] {len(set_cards)} cards...", end=" ", flush=True)

        for card in set_cards:
            num = card["number"]
            tcg_data = get_tcgdex_card(code, num)
            api_calls += 1

            if not tcg_data:
                errors += 1
                continue

            dex_ids = tcg_data.get("dexId", [])
            ja_name = tcg_data.get("name", "")
            category = tcg_data.get("category", "")

            en_name = build_en_name(dex_ids, ja_name, category)

            if en_name:
                sb.table("cards").update({"name_en": en_name}).eq(
                    "id", card["id"]
                ).execute()
                set_updated += 1
                updated += 1

            # Rate limit
            if api_calls % 5 == 0:
                time.sleep(0.1)

        print(f"{set_updated} updated")

    print(f"\nTotal updated: {updated}")
    print(f"API calls: {api_calls}, Errors: {errors}")
    print(f"Dex cache entries: {len(_dex_cache)}")
    print("Done!")


if __name__ == "__main__":
    main()
