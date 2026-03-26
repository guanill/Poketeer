"""
seed_ja_cards.py — Fetch cards from TCGdex API for any language and seed to Supabase.

Phase 1 (fast): Fetch set details only to get all cards with images.
Phase 2 (slow, optional): Fetch individual card details for extra fields (rarity, hp, etc.)
Phase 3 (optional): Fetch English names from EN TCGdex API for Latin character display.

Usage:
    pip install supabase python-dotenv requests
    python supabase/seed_ja_cards.py                # Japanese (default)
    python supabase/seed_ja_cards.py --lang th       # Thai
    python supabase/seed_ja_cards.py --lang ja --full # Japanese + full details + English names
    python supabase/seed_ja_cards.py --lang ja --art-cards  # List all Japanese art cards
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

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

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.seed")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BATCH = 500
session = requests.Session()

def get_lang():
    for i, arg in enumerate(sys.argv):
        if arg == "--lang" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return "ja"

LANG = get_lang()
TCGDEX_BASE = f"https://api.tcgdex.net/v2/{LANG}"
TCGDEX_EN = "https://api.tcgdex.net/v2/en"

# Japanese art card rarity identifiers
ART_CARD_RARITIES = {
    "Art Rare", "AR",
    "Special Art Rare", "SAR",
    "Character Rare", "CHR",
    "Character Super Rare", "CSR",
    "Illustration Rare", "IR",
    "Special Illustration Rare", "SIR",
    "Ultra Rare", "UR",
    "Hyper Rare", "HR",
    "Super Rare", "SR",
    "S", "A", "AR", "SAR", "HR", "UR", "SR",
    "Shiny Rare", "Shiny Super Rare",
}


def upsert_batch(table: str, rows: list[dict], batch_size: int = BATCH):
    total = len(rows)
    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        sb.table(table).upsert(batch).execute()
        done = min(i + batch_size, total)
        print(f"  {table}: {done}/{total}", end="\r")
    print(f"  {table}: {total}/{total} done")


def fetch_json(url: str):
    resp = session.get(url, timeout=30)
    if resp.status_code == 429:
        print("  Rate limited, waiting 5s...")
        time.sleep(5)
        resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Phase 1: Fetch sets + basic card info (fast — 1 request per set)
# ---------------------------------------------------------------------------

def phase1():
    print(f"\n[Phase 1] Fetching {LANG.upper()} sets from TCGdex...")
    sets_list = fetch_json(f"{TCGDEX_BASE}/sets/")
    print(f"  Found {len(sets_list)} sets")

    sets_dict: dict[str, dict] = {}
    cards_dict: dict[str, dict] = {}
    errors = []

    # Deduplicate set IDs from the list
    unique_set_ids = list(dict.fromkeys(s["id"] for s in sets_list))
    print(f"  Unique sets: {len(unique_set_ids)}")

    for i, set_id in enumerate(unique_set_ids):
        print(f"  Fetching set {i+1}/{len(unique_set_ids)}: {set_id}...", end="\r")

        try:
            # URL-encode set ID to handle + and other special chars
            detail = fetch_json(f"{TCGDEX_BASE}/sets/{quote(set_id, safe='')}")
        except Exception as e:
            errors.append((set_id, str(e)))
            continue

        # Build set row
        serie = detail.get("serie", {})
        card_count = detail.get("cardCount", {})
        supabase_set_id = f"{set_id}-{LANG}"

        sets_dict[supabase_set_id] = {
            "id": supabase_set_id,
            "name": detail.get("name", ""),
            "series": serie.get("name", ""),
            "printed_total": card_count.get("official", 0),
            "total": card_count.get("total", 0),
            "release_date": detail.get("releaseDate", ""),
            "language": LANG,
            "symbol_url": detail.get("symbol", ""),
            "logo_url": detail.get("logo", ""),
        }

        # Build card rows from set detail
        cards = detail.get("cards", [])
        for c in cards:
            card_id_raw = c.get("id", "")
            image_base = c.get("image", "")
            card_key = f"{card_id_raw}-{LANG}"

            cards_dict[card_key] = {
                "id": card_key,
                "name": c.get("name", ""),
                "number": c.get("localId", ""),
                "set_id": supabase_set_id,
                "rarity": "",
                "image_small": f"{image_base}/low.webp" if image_base else "",
                "image_large": f"{image_base}/high.webp" if image_base else "",
                "supertype": "",
                "subtypes": [],
                "hp": "",
                "artist": "",
                "types": [],
                "name_en": "",
            }

        # Small delay to be nice to the API
        time.sleep(0.1)

    all_sets = list(sets_dict.values())
    all_cards = list(cards_dict.values())
    print(f"\n  Sets: {len(all_sets)}, Cards: {len(all_cards)}, Errors: {len(errors)}")

    if errors:
        print("  Failed sets:", [e[0] for e in errors])

    if all_sets:
        print("\n  Upserting sets...")
        upsert_batch("sets", all_sets)

    if all_cards:
        print("  Upserting cards...")
        upsert_batch("cards", all_cards)

    return all_cards


# ---------------------------------------------------------------------------
# Phase 2: Fetch individual card details for extra fields (slow)
# ---------------------------------------------------------------------------

def phase2(card_ids: list[str]):
    print(f"\n[Phase 2] Fetching details for {len(card_ids)} cards...")
    print("  This will take a while...\n")

    updates = []
    errors = []

    for i, full_id in enumerate(card_ids):
        # Remove the -ja suffix to get the TCGdex ID
        tcgdex_id = full_id.removesuffix(f"-{LANG}")

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(card_ids)}")

        try:
            detail = fetch_json(f"{TCGDEX_BASE}/cards/{tcgdex_id}")
        except Exception as e:
            errors.append((tcgdex_id, str(e)))
            continue

        updates.append({
            "id": full_id,
            "rarity": detail.get("rarity", "") or "",
            "supertype": detail.get("category", "") or "",
            "subtypes": [detail["stage"]] if detail.get("stage") else [],
            "hp": str(detail.get("hp", "")) if detail.get("hp") else "",
            "artist": detail.get("illustrator", "") or "",
            "types": detail.get("types") or [],
        })

        time.sleep(0.05)

    print(f"\n  Updated: {len(updates)}, Errors: {len(errors)}")

    if updates:
        upsert_batch("cards", updates)


# ---------------------------------------------------------------------------
# Phase 3: Fetch English names from EN TCGdex API
# ---------------------------------------------------------------------------

def _fetch_en_name(tcgdex_id: str) -> tuple[str, str]:
    """Fetch a single card's English name. Returns (tcgdex_id, english_name)."""
    try:
        detail = fetch_json(f"{TCGDEX_EN}/cards/{quote(tcgdex_id, safe='')}")
        return (tcgdex_id, detail.get("name", ""))
    except Exception:
        return (tcgdex_id, "")


def phase3(cards: list[dict]):
    print(f"\n[Phase 3] Fetching English names for {len(cards)} cards...")

    # Build mapping: tcgdex_id -> supabase_id
    id_map: dict[str, str] = {}
    for c in cards:
        full_id = c["id"]
        tcgdex_id = full_id.removesuffix(f"-{LANG}")
        id_map[tcgdex_id] = full_id

    updates = []
    errors = 0

    # Use thread pool for faster fetching (8 concurrent requests)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_en_name, tid): tid
            for tid in id_map.keys()
        }

        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            if done_count % 100 == 0:
                print(f"  Progress: {done_count}/{len(futures)}")

            tcgdex_id, en_name = future.result()
            if en_name:
                updates.append({
                    "id": id_map[tcgdex_id],
                    "name_en": en_name,
                })
            else:
                errors += 1

    print(f"\n  English names found: {len(updates)}, Missing: {errors}")

    if updates:
        upsert_batch("cards", updates)


# ---------------------------------------------------------------------------
# Art cards report: find all art cards in Japanese sets
# ---------------------------------------------------------------------------

def find_art_cards():
    """Fetch all Japanese cards and identify art cards by rarity."""
    print(f"\n{'=' * 60}")
    print(f"Finding all art cards in {LANG.upper()} sets...")
    print(f"{'=' * 60}")

    sets_list = fetch_json(f"{TCGDEX_BASE}/sets/")
    unique_set_ids = list(dict.fromkeys(s["id"] for s in sets_list))

    art_cards: list[dict] = []
    all_rarities: set[str] = set()
    total_cards = 0

    for i, set_id in enumerate(unique_set_ids):
        print(f"  Scanning set {i+1}/{len(unique_set_ids)}: {set_id}...", end="\r")

        try:
            detail = fetch_json(f"{TCGDEX_BASE}/sets/{quote(set_id, safe='')}")
        except Exception:
            continue

        set_name = detail.get("name", set_id)
        cards = detail.get("cards", [])
        total_cards += len(cards)

        for c in cards:
            card_id = c.get("id", "")
            # Fetch individual card for rarity
            try:
                card_detail = fetch_json(f"{TCGDEX_BASE}/cards/{quote(card_id, safe='')}")
            except Exception:
                continue

            rarity = card_detail.get("rarity", "") or ""
            if rarity:
                all_rarities.add(rarity)

            # Check if this is an art card
            is_art = rarity in ART_CARD_RARITIES

            if is_art:
                # Also try to get the English name
                en_name = ""
                try:
                    en_detail = fetch_json(f"{TCGDEX_EN}/cards/{quote(card_id, safe='')}")
                    en_name = en_detail.get("name", "")
                except Exception:
                    pass

                art_cards.append({
                    "id": card_id,
                    "name_ja": card_detail.get("name", ""),
                    "name_en": en_name,
                    "set_id": set_id,
                    "set_name": set_name,
                    "number": card_detail.get("localId", ""),
                    "rarity": rarity,
                    "artist": card_detail.get("illustrator", ""),
                    "image": card_detail.get("image", ""),
                })

            time.sleep(0.03)

        time.sleep(0.1)

    # Print results
    print(f"\n\n{'=' * 60}")
    print(f"ART CARDS REPORT")
    print(f"{'=' * 60}")
    print(f"Total cards scanned: {total_cards}")
    print(f"Art cards found: {len(art_cards)}")
    print(f"\nAll rarities encountered: {sorted(all_rarities)}")

    # Group by rarity
    by_rarity: dict[str, list] = {}
    for ac in art_cards:
        r = ac["rarity"]
        by_rarity.setdefault(r, []).append(ac)

    print(f"\n{'─' * 60}")
    for rarity, cards in sorted(by_rarity.items()):
        print(f"\n  {rarity} ({len(cards)} cards):")
        for c in cards:
            en = f" ({c['name_en']})" if c["name_en"] else ""
            print(f"    #{c['number']:>4s}  {c['name_ja']}{en}  [{c['set_name']}]  by {c['artist']}")

    # Save to JSON
    output_path = ROOT / "backend" / f"art_cards_{LANG}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(art_cards, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {output_path}")

    return art_cards


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    full_mode = "--full" in sys.argv
    art_mode = "--art-cards" in sys.argv

    if art_mode:
        find_art_cards()
        return

    print("=" * 60)
    print(f"Seeding {LANG.upper()} cards from TCGdex API")
    print(f"  Mode: {'Full (sets + cards + details + EN names)' if full_mode else 'Fast (sets + cards with images)'}")
    print(f"  URL: {SUPABASE_URL}")
    print("=" * 60)

    start = time.time()

    cards = phase1()

    if full_mode and cards:
        card_ids = [c["id"] for c in cards]
        phase2(card_ids)
        phase3(cards)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
