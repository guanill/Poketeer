"""
fill_sm_from_bulbapedia.py — Populate Sun & Moon Thai sets with card data
from Bulbapedia ATCG pages. These sets don't have searchable cards on
the Thai Pokemon site, so we use Bulbapedia for names and card counts.

Card images use the Thai site's known URL pattern.
"""

import io
import os
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; Pokemon TCG scraper)"})

BULBA = "https://bulbapedia.bulbagarden.net"

# Map our set IDs to Bulbapedia page names and which sub-set (A or B)
SM_SETS = [
    ("SM1a", "First_Impact_(ATCG)", "A"),
    ("SM1b", "First_Impact_(ATCG)", "B"),
    ("SM2a", "Legends_Awakened_(ATCG)", "A"),
    ("SM2b", "Legends_Awakened_(ATCG)", "B"),
    ("SM3a", "Hidden_Shadow_(ATCG)", "A"),
    ("SM3b", "Hidden_Shadow_(ATCG)", "B"),
    ("SM4a", "Sky_Ruler_(ATCG)", "A"),
    ("SM4b", "Sky_Ruler_(ATCG)", "B"),
    ("SM5a", "Double_Burst_(ATCG)", "A"),
    ("SM5b", "Double_Burst_(ATCG)", "B"),
    ("SM6a", "Legendary_Clash_(ATCG)", "A"),
    ("SM6b", "Legendary_Clash_(ATCG)", "B"),
]


def fetch_card_list(wiki_page: str, target_set: str) -> list[dict]:
    """Fetch card list from a Bulbapedia ATCG page for Set A or Set B."""
    url = f"{BULBA}/wiki/{wiki_page}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = []

    # Find card tables by looking for header row with "No." and "Card name"
    card_tables = []
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if first_row:
            header = first_row.get_text(" ", strip=True)
            if "Card name" in header and "No." in header:
                card_tables.append(table)

    # Skip the first table if it's a combined wrapper (has more cards than individual sets)
    # The real Set A and Set B tables are typically the 2nd and 3rd card tables
    if len(card_tables) >= 3:
        set_a_table = card_tables[1]
        set_b_table = card_tables[2]
    elif len(card_tables) == 2:
        set_a_table = card_tables[0]
        set_b_table = card_tables[1]
    else:
        return []

    target_table = set_a_table if target_set == "A" else set_b_table

    for row in target_table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        num_text = cells[0].get_text(strip=True)
        num_match = re.match(r"(\d+)", num_text)
        if not num_match:
            continue
        number = num_match.group(1).lstrip("0") or "0"

        # Card name is 3rd column (No., Mark, Card name)
        name = cells[2].get_text(strip=True)
        if not name:
            continue

        # Determine supertype from other cells
        full_text = row.get_text(" ", strip=True).lower()
        supertype = ""
        if any(w in full_text for w in ["supporter", "item", "stadium", "trainer"]):
            supertype = "Trainer"
        elif "energy" in full_text:
            supertype = "Energy"
        else:
            supertype = "Pokémon"

        cards.append({
            "number": number,
            "name_en": name,
            "supertype": supertype,
        })

    return cards


def main():
    print("=" * 60)
    print("Filling Sun & Moon Thai sets from Bulbapedia")
    print("=" * 60)

    # Cache fetched pages
    page_cache: dict[str, str] = {}

    total_added = 0

    for code, wiki_page, ab in SM_SETS:
        set_id = f"{code}-th"

        # Check if already has cards
        existing = sb.table("cards").select("id", count="exact", head=True).eq("set_id", set_id).execute()
        if (existing.count or 0) > 0:
            print(f"\n{code}: already has {existing.count} cards, skipping")
            continue

        print(f"\n{code} (Set {ab}): fetching from {wiki_page}...")
        cards = fetch_card_list(wiki_page, ab)
        print(f"  Found {len(cards)} cards from Bulbapedia")

        if not cards:
            print(f"  WARNING: No cards found!")
            continue

        # Build card rows
        rows = []
        seen = set()
        for c in cards:
            card_key = f"{code}-{c['number']}-th"
            if card_key in seen:
                card_key = f"{code}-{c['number']}-dup-th"
            seen.add(card_key)

            rows.append({
                "id": card_key,
                "name": c["name_en"],  # Use English name as primary (no Thai name available)
                "name_en": c["name_en"],
                "number": c["number"],
                "set_id": set_id,
                "rarity": "",
                "image_small": "",
                "image_large": "",
                "supertype": c["supertype"],
                "subtypes": [],
                "hp": "",
                "artist": "",
                "types": [],
            })

        # Upsert
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            sb.table("cards").upsert(batch).execute()

        # Update set totals
        sb.table("sets").update({
            "total": len(rows),
            "printed_total": len(rows),
        }).eq("id", set_id).execute()

        total_added += len(rows)
        print(f"  Added {len(rows)} cards to {set_id}")

        time.sleep(1)  # Be nice to Bulbapedia

    print(f"\nTotal cards added: {total_added}")
    print("Done!")


if __name__ == "__main__":
    main()
