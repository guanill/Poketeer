"""
fill_th_en_names_final.py — Final pass to fill remaining Thai card English
names from Bulbapedia ATCG pages.

Handles:
- SC1a/SC1b: Sword & Shield ATCG (Set A / Set B)
- MA1: Mega Evolution ATCG
- MA2: Blue Blaze ATCG
- MA3: (no direct ATCG page, try multiple sources)
- MA4: Void Blast ATCG
- SV7s/SV4a/SV11s: Extended numbering from JA expansion pages
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


def fetch_atcg_card_names(page: str, target_set: str = "") -> dict[str, str]:
    """
    Fetch card names from a Bulbapedia ATCG page.
    If target_set is "A" or "B", picks the corresponding sub-table.
    Otherwise returns all cards from the page.
    Returns {number: english_name}.
    """
    url = f"{BULBA}/wiki/{page}"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Error: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find card tables by looking for header with "No." and "Card name"
    card_tables = []
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if first_row:
            header = first_row.get_text(" ", strip=True)
            if "Card name" in header and "No." in header:
                card_tables.append(table)

    if not card_tables:
        return {}

    # Select the right table
    if target_set in ("A", "B"):
        if len(card_tables) >= 3:
            target_table = card_tables[1] if target_set == "A" else card_tables[2]
        elif len(card_tables) == 2:
            target_table = card_tables[0] if target_set == "A" else card_tables[1]
        else:
            target_table = card_tables[0]
        tables_to_parse = [target_table]
    else:
        # Use the largest table (skip small wrapper tables)
        tables_to_parse = card_tables

    name_map: dict[str, str] = {}
    for table in tables_to_parse:
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            num_text = cells[0].get_text(strip=True)
            num_match = re.match(r"(\d+)", num_text)
            if not num_match:
                continue
            num = num_match.group(1).lstrip("0") or "0"

            # Card name is in the 3rd column (index 2)
            name = cells[2].get_text(strip=True)
            if not name:
                # Try getting from a link
                for link in cells[2].find_all("a"):
                    t = link.get_text(strip=True)
                    if t and len(t) > 1:
                        name = t
                        break

            if name and num not in name_map:
                name_map[num] = name

    return name_map


def fetch_en_from_ja_expansion(page: str, ja_total: int) -> dict[str, str]:
    """
    Fetch English card names from a Bulbapedia JA expansion page.
    Handles extended numbering (secret rares beyond the base set size).
    """
    url = f"{BULBA}/wiki/{page}"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Error: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    name_map: dict[str, str] = {}

    # Find all tables that might contain the JA numbering
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if f"/{ja_total:03d}" not in text:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue

            row_text = " ".join(c.get_text(strip=True) for c in cells)
            # Match both regular (001/070) and secret rare (071/070+) numbers
            match = re.search(rf"(\d{{3}})/{ja_total:03d}", row_text)
            if not match:
                continue

            num = match.group(1).lstrip("0") or "0"

            name = ""
            for cell in cells:
                for link in cell.find_all("a"):
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    if not text or len(text) < 2:
                        continue
                    if "/wiki/" not in href:
                        continue
                    if any(s in href.lower() for s in ["file:", "category:", "special:"]):
                        continue
                    if text in ("Promotion", "Promo"):
                        continue
                    name = text
                    break
                if name:
                    break

            if name and num not in name_map:
                name_map[num] = name

    return name_map


def main():
    print("=" * 60)
    print("Final pass: filling remaining Thai card English names")
    print("=" * 60)

    # Get remaining missing cards
    all_missing: list[dict] = []
    offset = 0
    while True:
        data = (
            sb.table("cards")
            .select("id, name, number, set_id")
            .like("set_id", "%-th")
            .eq("name_en", "")
            .range(offset, offset + 999)
            .execute()
        )
        if not data.data:
            break
        all_missing.extend(data.data)
        if len(data.data) < 1000:
            break
        offset += 1000

    print(f"Found {len(all_missing)} TH cards still missing name_en\n")

    by_set: dict[str, list[dict]] = {}
    for card in all_missing:
        by_set.setdefault(card["set_id"], []).append(card)

    updates: list[tuple[str, str]] = []

    # ── SC1a / SC1b: Sword & Shield ATCG page ──
    for set_id, ab in [("SC1a-th", "A"), ("SC1b-th", "B")]:
        if set_id not in by_set:
            continue
        cards = by_set[set_id]
        print(f"{set_id} ({len(cards)} missing): Sword_%26_Shield_(ATCG) Set {ab}")
        name_map = fetch_atcg_card_names("Sword_%26_Shield_(ATCG)", ab)
        matched = 0
        for card in cards:
            en = name_map.get(card["number"]) or name_map.get(card["number"].zfill(3))
            if en:
                updates.append((card["id"], en))
                matched += 1
        print(f"  Matched {matched}/{len(cards)}")
        time.sleep(1)

    # ── MA sets: ATCG pages ──
    ma_mapping = {
        "MA1-th": ("Mega_Evolution_(ATCG)", ""),
        "MA2-th": ("Blue_Blaze_(ATCG)", ""),
        "MA4-th": ("Void_Blast_(ATCG)", ""),
    }

    for set_id, (page, ab) in ma_mapping.items():
        if set_id not in by_set:
            continue
        cards = by_set[set_id]
        print(f"\n{set_id} ({len(cards)} missing): {page}")
        name_map = fetch_atcg_card_names(page, ab)
        matched = 0
        for card in cards:
            en = name_map.get(card["number"]) or name_map.get(card["number"].zfill(3))
            if en:
                updates.append((card["id"], en))
                matched += 1
        print(f"  Matched {matched}/{len(cards)}")
        time.sleep(1)

    # MA3 might not have a single ATCG page - it's a large compilation (486 cards)
    # Try "Black_Shine_(ATCG)" or check if there's a specific page
    if "MA3-th" in by_set:
        cards = by_set["MA3-th"]
        print(f"\nMA3-th ({len(cards)} missing): trying multiple ATCG pages...")

        # MA3 "Mega Evolution Dream ex" - might be a new set
        # Try various ATCG pages
        ma3_pages = [
            "Black_Shine_(ATCG)",
            "Paradox_Encounters_(ATCG)",
            "Ace_Paradox_(ATCG)",
            "Transfiguration_Mask_(ATCG)",
        ]

        combined: dict[str, str] = {}
        for page in ma3_pages:
            names = fetch_atcg_card_names(page)
            if names:
                print(f"  {page}: {len(names)} names")
                combined.update(names)
            time.sleep(0.5)

        if combined:
            matched = 0
            for card in cards:
                en = combined.get(card["number"])
                if en:
                    updates.append((card["id"], en))
                    matched += 1
            print(f"  Matched {matched}/{len(cards)}")

    # ── SV extended numbering ──
    # SV7s: Stellar Miracle has JA total of 102
    # The TH extra cards (176+) correspond to JA secret rares (103+)
    # Need to figure out the number offset
    sv_expansion_pages = {
        "SV7s-th": [("Stellar_Miracle_(TCG)", 102)],
        "SV4a-th": [("Raging_Surf_(TCG)", 62)],
    }

    for set_id, sources in sv_expansion_pages.items():
        if set_id not in by_set:
            continue
        cards = by_set[set_id]
        print(f"\n{set_id} ({len(cards)} missing):")

        for page, ja_total in sources:
            print(f"  Trying {page} (/{ja_total:03d})...")
            name_map = fetch_en_from_ja_expansion(page, ja_total)

            if name_map:
                # Try direct number match first
                matched = 0
                for card in cards:
                    en = name_map.get(card["number"]) or name_map.get(card["number"].lstrip("0") or "0")
                    if en:
                        updates.append((card["id"], en))
                        matched += 1
                print(f"    Direct match: {matched}/{len(cards)}")

            time.sleep(1)

    # ── SV11s: Check if ATCG page exists ──
    if "SV11s-th" in by_set:
        cards = by_set["SV11s-th"]
        print(f"\nSV11s-th ({len(cards)} missing): trying ATCG pages...")

        sv11_pages = [
            "Sparkling_Fable_(ATCG)",
            "Stellar_Lightning_(ATCG)",
            "Bonds_of_Destiny_(ATCG)",
            "Presence_of_Champions_(ATCG)",
        ]

        for page in sv11_pages:
            names = fetch_atcg_card_names(page)
            if names:
                print(f"  {page}: {len(names)} names")
                matched = 0
                for card in cards:
                    if card["id"] in [u[0] for u in updates]:
                        continue
                    en = names.get(card["number"])
                    if en:
                        updates.append((card["id"], en))
                        matched += 1
                if matched:
                    print(f"    Matched {matched}")
            time.sleep(0.5)

    # ── Apply updates ──
    print(f"\n{'=' * 60}")
    print(f"Total updates: {len(updates)}")
    print(f"{'=' * 60}")

    if updates:
        print("\nApplying updates...")
        for i, (card_id, name_en) in enumerate(updates):
            sb.table("cards").update({"name_en": name_en}).eq("id", card_id).execute()
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(updates)}", end="\r")
        print(f"  {len(updates)}/{len(updates)} done")

    still = (
        sb.table("cards")
        .select("id", count="exact", head=True)
        .like("set_id", "%-th")
        .eq("name_en", "")
        .execute()
    )
    print(f"\nStill missing name_en: {still.count}")
    print("Done!")


if __name__ == "__main__":
    main()
