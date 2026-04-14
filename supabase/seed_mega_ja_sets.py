"""
seed_mega_ja_sets.py — Seed missing MEGA-era JA sets into Supabase.

Sets:
  M1-ja    Mega Brave     artofpkm/570   92 cards
  M2-ja    Inferno X      artofpkm/575  116 cards
  M2pt5-ja Mega Dream ex  artofpkm/579  252 cards
  M4-ja    Ninja Spinner  artofpkm/585  119 cards

Card names are extracted from artofpkm data-lightbox-title attributes (English).
Images are filled afterwards via fill_images_artofpkm.py.

Usage:
    python supabase/seed_mega_ja_sets.py           # seed all
    python supabase/seed_mega_ja_sets.py --set M1-ja
    python supabase/seed_mega_ja_sets.py --dry-run
"""

import io
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 poketeer-bot"

BASE = "https://www.artofpkm.com"

# MEGA sets to seed: db_set_id → (artofpkm_id, display_name, release_date)
SETS_TO_SEED = {
    "M1-ja":    (570, "Mega Brave",    "2025-01-24"),
    "M2-ja":    (575, "Inferno X",     "2025-03-28"),
    "M2pt5-ja": (579, "Mega Dream ex", "2025-06-06"),
    "M4-ja":    (585, "Ninja Spinner", "2025-08-08"),
}


def extract_card_entries(html: str) -> dict[int, str]:
    """Extract {card_number: card_name} from data-lightbox-title attrs.

    artofpkm anchor format (title comes before url):
      data-lightbox-title="Bulbasaur, Mega Brave" data-lightbox-url="/sets/N/card/NUM"
    """
    # title comes BEFORE url in the HTML
    matches = re.findall(
        r'data-lightbox-title="([^"]+)"[^>]*data-lightbox-url="/sets/\d+/card/(\d+)"',
        html,
    )
    result = {}
    for title, num in matches:
        # title is like "Bulbasaur, Mega Brave" — take everything before first comma
        name = title.split(",")[0].strip()
        result[int(num)] = name
    return result


def scrape_set_card_names(artofpkm_id: int) -> dict[int, str]:
    """Return {card_number: pokemon_name} for all cards in a set."""
    card_map: dict[int, str] = {}

    r = SESSION.get(f"{BASE}/sets/{artofpkm_id}", timeout=30)
    r.raise_for_status()
    card_map.update(extract_card_entries(r.text))

    offset = 100
    while True:
        r = SESSION.get(f"{BASE}/sets/{artofpkm_id}/card_batches?offset={offset}", timeout=30)
        r.raise_for_status()
        batch = extract_card_entries(r.text)
        if not batch:
            break
        card_map.update(batch)
        offset += 100
        time.sleep(0.1)

    return card_map


def get_set_total(artofpkm_id: int) -> int:
    """Fetch set page and extract total card count from the page title or stats."""
    r = SESSION.get(f"{BASE}/sets/{artofpkm_id}", timeout=30)
    r.raise_for_status()
    # Look for something like "116 Cards" or card count in meta
    m = re.search(r"(\d+)\s+Cards?", r.text, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def set_exists(set_id: str) -> bool:
    res = sb.table("sets").select("id").eq("id", set_id).execute()
    return bool(res.data)


def card_count(set_id: str) -> int:
    res = sb.table("cards").select("id", count="exact").eq("set_id", set_id).execute()
    return res.count or 0


def seed_set(set_id: str, artofpkm_id: int, display_name: str, release_date: str, dry_run: bool = False) -> None:
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {set_id} — {display_name} (artofpkm/{artofpkm_id})")

    if set_exists(set_id):
        existing = card_count(set_id)
        print(f"  Set already in DB with {existing} cards")
        if existing > 0:
            print(f"  Skipping (already seeded). Use --force to re-seed.")
            return
    else:
        print(f"  Set not in DB, will create")

    print(f"  Scraping card names from artofpkm...")
    try:
        card_names = scrape_set_card_names(artofpkm_id)
    except Exception as e:
        print(f"  ERROR scraping: {e}")
        return

    if not card_names:
        print(f"  No card names found, aborting")
        return

    total = max(card_names.keys())
    print(f"  Found {len(card_names)} cards (max position: {total})")

    # Build set row
    set_row = {
        "id": set_id,
        "name": display_name,
        "series": "Mega",
        "printed_total": total,
        "total": total,
        "release_date": release_date,
        "language": "ja",
    }

    if not dry_run:
        sb.table("sets").upsert(set_row).execute()
        print(f"  Upserted set row")
    else:
        print(f"  Would upsert set: {set_row}")

    # Build card rows
    # ID format: M1-001-ja, M2pt5-042-ja, etc.
    base_id = set_id.removesuffix("-ja")  # e.g. "M1", "M2pt5"
    card_rows = []
    for pos in range(1, total + 1):
        name = card_names.get(pos, f"Card {pos}")
        card_id = f"{base_id}-{pos:03d}-ja"
        card_rows.append({
            "id": card_id,
            "name": name,
            "name_en": name,
            "number": str(pos),
            "set_id": set_id,
            "rarity": "",
            "image_small": "",
            "image_large": "",
            "supertype": "",
            "subtypes": [],
            "hp": "",
            "artist": "",
            "types": [],
        })

    print(f"  Prepared {len(card_rows)} card rows")

    if dry_run:
        for r in card_rows[:5]:
            print(f"    {r['id']}: {r['name']}")
        if len(card_rows) > 5:
            print(f"    ... and {len(card_rows) - 5} more")
        return

    # Upsert cards in batches
    for i in range(0, len(card_rows), 200):
        chunk = card_rows[i : i + 200]
        sb.table("cards").upsert(chunk).execute()
        print(f"  {min(i + 200, len(card_rows))}/{len(card_rows)} cards upserted", end="\r")
    print()
    print(f"  Done seeding {set_id}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", help="Only process this set (e.g. M1-ja)")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    ap.add_argument("--force", action="store_true", help="Re-seed even if cards exist")
    args = ap.parse_args()

    targets = SETS_TO_SEED
    if args.set:
        if args.set not in SETS_TO_SEED:
            print(f"ERROR: {args.set} not in SETS_TO_SEED. Valid: {list(SETS_TO_SEED)}")
            sys.exit(1)
        targets = {args.set: SETS_TO_SEED[args.set]}

    print(f"Seeding {len(targets)} MEGA JA set(s)...")
    for set_id, (artofpkm_id, display_name, release_date) in targets.items():
        seed_set(set_id, artofpkm_id, display_name, release_date, dry_run=args.dry_run)

    print("\nAll done!")


if __name__ == "__main__":
    main()
