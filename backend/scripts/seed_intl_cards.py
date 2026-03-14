"""
seed_intl_cards.py — Fetch Japanese & Thai cards from tcgdex.net
and seed them into Supabase.

Also updates set logos using EN equivalents from pokemontcg.io
(the set symbol/icon is language-neutral).

Usage:
    pip install supabase python-dotenv requests
    python backend/scripts/seed_intl_cards.py
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.seed")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

TCGDEX_API = "https://api.tcgdex.net/v2"
HEADERS = {"User-Agent": "poketeer/1.0"}

# Map JA set IDs to EN pokemontcg.io IDs for logo/symbol images
SET_ID_MAP = {
    "SV1S": "sv1", "SV1V": "sv1", "SV1a": "sv1",
    "SV2P": "sv2", "SV2D": "sv2", "SV2a": "sv3pt5",
    "SV3": "sv3", "SV3a": "sv3",
    "SV4K": "sv4", "SV4M": "sv4", "SV4a": "sv4pt5",
    "SV5K": "sv5", "SV5M": "sv5", "SV5a": "sv5",
    "SV6": "sv6", "SV6a": "sv6",
    "SV7": "sv7", "SV7a": "sv7",
    "SV8": "sv8", "SV8a": "sv8",
    "SV9": "sv9", "SV9a": "sv9",
    "SV10": "sv10",
    "SV11W": "sv10", "SV11B": "sv10",
}


def ja_to_en_id(set_id: str) -> str | None:
    """Try to map a JA set ID to an EN pokemontcg.io set ID."""
    if set_id in SET_ID_MAP:
        return SET_ID_MAP[set_id]
    # Try auto-mapping: SV9 -> sv9, SV10 -> sv10
    m = re.match(r"^(SV|BW|XY|SM|SWSH)(\d+)([a-zA-Z]?)$", set_id)
    if m:
        prefix = m.group(1).lower()
        num = m.group(2)
        suffix = m.group(3).lower()
        if not suffix:
            return f"{prefix}{num}"
    return None


def update_set_logos():
    """Update JA/TH sets with EN logo/symbol from pokemontcg.io."""
    print("\n[1/3] Updating set logos...")

    for lang in ["ja", "th"]:
        lang_file = ROOT / "backend" / f"sets_{lang}.json"
        if not lang_file.exists():
            continue

        with open(lang_file, encoding="utf-8") as f:
            sets = json.load(f)

        updated = 0
        for s in sets:
            en_id = ja_to_en_id(s["id"])
            if not en_id:
                continue

            logo_url = f"https://images.pokemontcg.io/{en_id}/logo.png"
            symbol_url = f"https://images.pokemontcg.io/{en_id}/symbol.png"

            # Quick check if the logo exists
            try:
                r = requests.head(logo_url, timeout=5)
                if r.status_code == 200:
                    s["images"]["logo"] = logo_url
                    s["images"]["symbol"] = symbol_url
                    updated += 1
            except:
                pass

        # Save updated JSON
        with open(lang_file, "w", encoding="utf-8") as f:
            json.dump(sets, f, ensure_ascii=False, indent=2)

        # Update Supabase
        rows = []
        for s in sets:
            images = s.get("images", {})
            rows.append({
                "id": f"{s['id']}-{lang}",
                "name": s.get("name", ""),
                "series": s.get("series", ""),
                "printed_total": s.get("printedTotal", 0),
                "total": s.get("total", 0),
                "release_date": s.get("releaseDate", ""),
                "language": lang,
                "symbol_url": images.get("symbol", ""),
                "logo_url": images.get("logo", ""),
            })

        for i in range(0, len(rows), 100):
            sb.table("sets").upsert(rows[i:i+100]).execute()

        print(f"  {lang}: {updated}/{len(sets)} sets now have logos")


def fetch_cards_for_set(lang: str, set_id: str) -> list[dict]:
    """Fetch all cards for a set from tcgdex."""
    try:
        r = requests.get(
            f"{TCGDEX_API}/{lang}/sets/{set_id}",
            headers=HEADERS, timeout=15
        )
        if r.status_code != 200:
            return []
        data = r.json()
        cards_summary = data.get("cards", [])

        result = []
        for c in cards_summary:
            card_id = c.get("id", "")
            local_id = c.get("localId", "")
            name = c.get("name", "")
            image_base = c.get("image", "")

            result.append({
                "id": f"{card_id}-{lang}",  # Make unique per language
                "name": name,
                "number": local_id,
                "set_id": f"{set_id}-{lang}",  # References the lang-suffixed set
                "rarity": "",
                "image_small": f"{image_base}/high.webp" if image_base else "",
                "image_large": f"{image_base}/high.png" if image_base else "",
                "supertype": "",
                "subtypes": [],
                "hp": "",
                "artist": "",
                "types": [],
            })
        return result
    except Exception as e:
        print(f"    Error fetching {lang}/{set_id}: {e}")
        return []


def fetch_card_details(lang: str, card_id: str) -> dict | None:
    """Fetch full card details for rarity, types, etc."""
    try:
        r = requests.get(
            f"{TCGDEX_API}/{lang}/cards/{card_id}",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


def seed_intl_cards():
    """Fetch and seed JA/TH cards."""
    print("\n[2/3] Fetching international cards...")

    for lang in ["ja", "th"]:
        lang_file = ROOT / "backend" / f"sets_{lang}.json"
        if not lang_file.exists():
            print(f"  Skipping {lang} (no sets file)")
            continue

        with open(lang_file, encoding="utf-8") as f:
            sets = json.load(f)

        print(f"\n  {lang.upper()}: {len(sets)} sets")
        all_cards = []

        for i, s in enumerate(sets):
            set_id = s["id"]
            cards = fetch_cards_for_set(lang, set_id)
            all_cards.extend(cards)
            if (i + 1) % 10 == 0 or i == len(sets) - 1:
                print(f"    {i+1}/{len(sets)} sets fetched ({len(all_cards)} cards)")
            time.sleep(0.1)  # Rate limiting

        print(f"  Total: {len(all_cards)} {lang.upper()} cards")

        # Seed to Supabase in batches
        if all_cards:
            BATCH = 500
            for i in range(0, len(all_cards), BATCH):
                batch = all_cards[i:i+BATCH]
                try:
                    sb.table("cards").upsert(batch).execute()
                except Exception as e:
                    print(f"    Batch {i} failed: {e}")
                done = min(i + BATCH, len(all_cards))
                print(f"    Seeded {done}/{len(all_cards)}", end="\r")
            print(f"    Seeded {len(all_cards)}/{len(all_cards)} {lang.upper()} cards")


def verify():
    """Quick verification."""
    print("\n[3/3] Verifying...")
    for lang in ["en", "ja", "th"]:
        res = sb.table("cards").select("id", count="exact", head=True).like("id", f"%-{lang}" if lang != "en" else "%").execute()
        # Just count cards per language by checking set language
        res = sb.table("sets").select("id", count="exact", head=True).eq("language", lang).execute()
        print(f"  {lang}: {res.count} sets")


def main():
    print("=" * 60)
    print("Seeding international cards to Supabase")
    print("=" * 60)

    t0 = time.time()
    update_set_logos()
    seed_intl_cards()
    verify()
    print(f"\nDone in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
