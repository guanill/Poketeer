"""
fill_en_names_bulk.py — Fill English names for ALL JA and TH cards
by fetching from TCGdex EN API.

The EN sets have different IDs (sv06 vs SV6), so we fetch the full EN
set, then match cards by localId (card number within the set).

Usage:
    python supabase/fill_en_names_bulk.py
"""

import io
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))
session = requests.Session()
TCGDEX_EN = "https://api.tcgdex.net/v2/en"


def fetch_json(url):
    resp = session.get(url, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_en_set_names(en_set_id: str) -> dict[str, str]:
    """Fetch all card names from an EN TCGdex set. Returns {localId: name}."""
    data = fetch_json(f"{TCGDEX_EN}/sets/{quote(en_set_id, safe='')}")
    if not data:
        return {}
    result = {}
    for c in data.get("cards", []):
        local_id = c.get("localId", "")
        name = c.get("name", "")
        if local_id and name:
            # Strip leading zeros to match our DB format
            num = local_id.lstrip("0") or "0"
            result[num] = name
            # Also store with leading zeros
            result[local_id] = name
    return result


# Map JA/TH set codes → EN TCGdex set IDs
# JA uses codes like SV6, SV8a etc.
# EN uses sv06, sv08.5 etc.
# We fetch ALL EN sets first to build this automatically.
def build_set_mapping() -> dict[str, str]:
    """Build a mapping from JA set codes to EN TCGdex set IDs.
    We match by fetching each EN set's card details."""

    # Hardcoded mapping for known sets (JA code → EN TCGdex ID)
    return {
        # Scarlet & Violet
        "SV1S": "sv01", "SV1V": "sv01",
        "SV1a": "sv03.5",  # Triple Beat → 151 (approximate)
        "SV2D": "sv02", "SV2P": "sv02",
        "SV2a": "sv03.5",  # Pokemon Card 151
        "SV3": "sv03",     # Ruler of Black Flame → Obsidian Flames
        "SV3a": "sv06.5",  # Raging Surf
        "SV4K": "sv04", "SV4M": "sv04",  # Ancient/Future → Paradox Rift
        "SV4a": "sv04.5",  # Shiny Treasure → Paldean Fates
        "SV5K": "sv05", "SV5M": "sv05",  # Wild Force/Cyber Judge → Temporal Forces
        "SV5a": "sv06",    # Crimson Haze → Twilight Masquerade
        "SV6": "sv06",     # Mask of Change → Twilight Masquerade
        "SV7s": "sv07",    # Stellar Miracle → Stellar Crown
        "SV8s": "sv08",    # Stellar Thunder → Surging Sparks
        "SV8a": "sv08.5",  # Terastal Festival → Prismatic Evolutions
        "SV9s": "sv09",    # Threads of Fate → Journey Together
        "SV10s": "sv10",   # Rise of Undefeated → Destined Rivals
        # Sword & Shield
        "S5I": None, "S5R": None, "S5a": None,
        "S8": None, "S8a": None, "S8b": None,
        "S9": None, "S9a": None,
        "S10a": None, "S10b": None, "S10D": None, "S10P": None,
        "S11": None, "S11a": None,
        "S12": None, "S12a": None,
        # Mega Evolution (too new, no EN equivalent)
        "MA1": None, "MA2": None, "MA3": None, "MA4": None,
    }


def main():
    print("=" * 60)
    print("Filling English names for JA + TH cards (bulk)")
    print("=" * 60)

    mapping = build_set_mapping()

    # Fetch EN names for each mapped set
    en_names_by_set: dict[str, dict[str, str]] = {}
    for ja_code, en_id in mapping.items():
        if not en_id:
            continue
        if en_id not in en_names_by_set:
            print(f"  Fetching EN set {en_id}...", end=" ")
            names = fetch_en_set_names(en_id)
            en_names_by_set[en_id] = names
            print(f"{len(names)} cards")
            time.sleep(0.2)

    # Now get all JA and TH cards without name_en
    print("\nFetching cards without name_en...")
    cards_to_update = []
    for lang_suffix in ["-ja", "-th"]:
        page = 0
        while True:
            res = (sb.table("cards")
                   .select("id, number, set_id")
                   .like("set_id", f"%{lang_suffix}")
                   .eq("name_en", "")
                   .range(page * 1000, (page + 1) * 1000 - 1)
                   .execute())
            if not res.data:
                break
            cards_to_update.extend(res.data)
            page += 1

    print(f"  Found {len(cards_to_update)} cards\n")

    # Match and update
    updated = 0
    skipped_sets = set()

    for i, card in enumerate(cards_to_update):
        set_id = card["set_id"]
        # Extract set code: "SV6-ja" → "SV6", "SV6-th" → "SV6"
        code = set_id.split("-")[0]
        if len(set_id.split("-")) > 2:
            code = "-".join(set_id.split("-")[:-1])  # handle codes like "SV-P"

        en_id = mapping.get(code)
        if not en_id:
            skipped_sets.add(code)
            continue

        names = en_names_by_set.get(en_id, {})
        en_name = names.get(card["number"]) or names.get(card["number"].zfill(3))

        if en_name:
            sb.table("cards").update({"name_en": en_name}).eq("id", card["id"]).execute()
            updated += 1

        if (i + 1) % 200 == 0:
            print(f"  Progress: {i + 1}/{len(cards_to_update)} (updated: {updated})", end="\r")

    print(f"  Progress: {len(cards_to_update)}/{len(cards_to_update)} (updated: {updated})")
    print(f"\nUpdated {updated} cards with English names")
    if skipped_sets:
        print(f"Skipped sets (no EN equivalent): {sorted(skipped_sets)}")
    print("\nDone!")


if __name__ == "__main__":
    main()
