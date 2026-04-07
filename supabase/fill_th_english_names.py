"""
fill_th_english_names.py — Fill English names for Thai cards.

Strategy:
1. Try matching by number against JA/EN cards already in Supabase
2. For remaining, fetch from TCGdex EN API by set code + card number

Usage:
    python supabase/fill_th_english_names.py
"""

import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

TCGDEX_EN = "https://api.tcgdex.net/v2/en"
session = requests.Session()

# Map Thai set code → TCGdex EN set ID for API lookups
TH_TO_TCGDEX = {
    "MA4": "MA4", "MA3": "MA3", "MA2": "MA2", "MA1": "MA1",
    "SV10s": "SV10s", "SV9s": "SV9s", "SV8a": "SV8a", "SV8s": "SV8s",
    "SV7s": "SV7s", "SV6": "SV6", "SV5M": "SV5M", "SV5K": "SV5K",
    "SV5a": "SV5a", "SV4a": "SV4a", "SV4M": "SV4M", "SV4K": "SV4K",
    "SV3": "SV3", "SV3a": "SV3a", "SV2a": "SV2a", "SV2P": "SV2P",
    "SV2D": "SV2D", "SV1S": "SV1S", "SV1V": "SV1V", "SVDs": "SVDs",
    "SVHK": "SVHK", "SVHM": "SVHM",
    "S12a": "S12a", "S12": "S12", "S5a": "S5a", "S5R": "S5R",
    "S5I": "S5I", "S10a": "S10a",
}


def fetch_en_name_from_tcgdex(set_code: str, number: str) -> str:
    """Try fetching English name from TCGdex for a card."""
    # TCGdex card ID format: {setId}-{localId}
    padded = number.zfill(3)
    for num_variant in [number, padded]:
        card_id = f"{set_code}-{num_variant}"
        try:
            resp = session.get(
                f"{TCGDEX_EN}/cards/{quote(card_id, safe='')}",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("name", "")
        except Exception:
            pass
    return ""


def main():
    print("Filling English names for Thai cards...\n")

    # Get all Thai cards without English names
    print("Fetching Thai cards...")
    th_cards = []
    page = 0
    while True:
        res = (sb.table("cards")
               .select("id, number, set_id, name_en")
               .like("set_id", "%-th")
               .eq("name_en", "")
               .range(page * 1000, (page + 1) * 1000 - 1)
               .execute())
        if not res.data:
            break
        th_cards.extend(res.data)
        page += 1
    print(f"  Found {len(th_cards)} Thai cards without English names\n")

    if not th_cards:
        print("Nothing to do!")
        return

    # Group by set code
    by_set: dict[str, list[dict]] = {}
    for c in th_cards:
        code = c["set_id"].removesuffix("-th")
        by_set.setdefault(code, []).append(c)

    # Step 1: Try matching from existing JA cards in Supabase
    updates: list[dict] = []
    remaining: list[dict] = []

    for code, cards in by_set.items():
        ja_set_id = f"{code}-ja"
        name_map: dict[str, str] = {}

        ref_page = 0
        while True:
            res = (sb.table("cards")
                   .select("number, name, name_en")
                   .eq("set_id", ja_set_id)
                   .range(ref_page * 1000, (ref_page + 1) * 1000 - 1)
                   .execute())
            if not res.data:
                break
            for r in res.data:
                en = r.get("name_en") or ""
                if en and r["number"] not in name_map:
                    name_map[r["number"]] = en
            ref_page += 1

        matched = 0
        for c in cards:
            en = name_map.get(c["number"], "")
            if en:
                updates.append({"id": c["id"], "name_en": en})
                matched += 1
            else:
                remaining.append(c)

        if matched:
            print(f"[{code}] DB match: {matched}/{len(cards)}")

    print(f"\nDB matches: {len(updates)}, remaining: {len(remaining)}")

    # Step 2: Fetch remaining from TCGdex EN API
    if remaining:
        print(f"\nFetching {len(remaining)} names from TCGdex EN API...")

        def fetch_one(card: dict) -> tuple[str, str]:
            code = card["set_id"].removesuffix("-th")
            tcgdex_set = TH_TO_TCGDEX.get(code, code)
            en_name = fetch_en_name_from_tcgdex(tcgdex_set, card["number"])
            return card["id"], en_name

        api_found = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fetch_one, c): c for c in remaining}
            done = 0
            for future in as_completed(futures):
                done += 1
                if done % 50 == 0:
                    print(f"  Progress: {done}/{len(remaining)} (found: {api_found})", end="\r")
                card_id, en_name = future.result()
                if en_name:
                    updates.append({"id": card_id, "name_en": en_name})
                    api_found += 1
                time.sleep(0.02)

        print(f"  TCGdex matches: {api_found}/{len(remaining)}          ")

    # Step 3: Update Supabase (only name_en field, using individual updates)
    if updates:
        print(f"\nUpdating {len(updates)} cards with English names...")
        total = len(updates)
        for i, u in enumerate(updates):
            sb.table("cards").update({"name_en": u["name_en"]}).eq("id", u["id"]).execute()
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{total}", end="\r")
        print(f"  {total}/{total} done")
    else:
        print("\nNo matches found.")

    print("\nDone!")


if __name__ == "__main__":
    main()
