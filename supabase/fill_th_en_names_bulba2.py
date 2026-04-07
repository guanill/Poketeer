"""
fill_th_en_names_bulba2.py — Second pass: Fill remaining Thai card English
names using Bulbapedia, handling:
1. SC sets: extra cards from S1a, S2, S2a, S3, S3a, S4, S4a sets
2. SV secret rares: match by position in the extended list
3. SV8a: Terastal Fest ex
4. MA sets: Thai-exclusive compilation sets

For SC sets, the Thai SC1a/SC1b/SC3a/SC3b sets compile cards from
multiple JA sets. The cards beyond the base JA set come from other
JA expansions.
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


def fetch_all_card_names_from_page(page: str) -> dict[str, str]:
    """
    Fetch ALL card names from a Bulbapedia TCG page.
    Returns {number: english_name} for ALL number patterns found.
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

    # Find the main card list table (the one with "No." and "Card name" headers)
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        header_text = first_row.get_text(" ", strip=True)
        if "Card name" not in header_text:
            continue
        if "No." not in header_text:
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Get number from first cell
            num_text = cells[0].get_text(strip=True)
            num_match = re.match(r"(\d+)", num_text)
            if not num_match:
                continue
            num = num_match.group(1).lstrip("0") or "0"

            # Get card name from link in cells
            name = ""
            for cell in cells[1:4]:  # Check cells 1-3
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

            # Fallback: get text from cell 2 directly
            if not name and len(cells) > 2:
                name = cells[2].get_text(strip=True)
                # Clean up
                name = re.sub(r"\s*\(TCG\)\s*$", "", name)

            if name and num not in name_map:
                name_map[num] = name

    return name_map


def fetch_en_names_from_combined_table(page: str, ja_total: int) -> dict[str, str]:
    """
    Fetch card names from a Bulbapedia EN expansion page that has a combined table
    with both EN and JA numbering.
    Returns {ja_number: english_name}.
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
    ja_pattern = re.compile(rf"(\d{{3}})/{ja_total:03d}")

    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if f"/{ja_total:03d}" not in text:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue

            row_text = " ".join(c.get_text(strip=True) for c in cells)
            ja_match = ja_pattern.search(row_text)
            if not ja_match:
                continue

            num = ja_match.group(1).lstrip("0") or "0"

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
    print("Second pass: filling remaining Thai card English names")
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

    # ── SC1a extra cards (61-154): from S1a VMAX Rising + S2 Rebellion Crash
    for sc_set, extra_sources in [
        ("SC1a-th", [
            ("VMAX_Rising_(TCG)", 70),     # S1a
            ("Rebellion_Crash_(TCG)", 96),  # S2
        ]),
        ("SC1b-th", [
            ("VMAX_Rising_(TCG)", 70),     # S1a
            ("Rebellion_Crash_(TCG)", 96),  # S2
        ]),
        ("SC3a-th", [
            ("Explosive_Walker_(TCG)", 70),   # S2a
            ("Infinity_Zone_(TCG)", 100),     # S3
            ("Legendary_Heartbeat_(TCG)", 76), # S3a
            ("Amazing_Volt_Tackle_(TCG)", 100), # S4
        ]),
        ("SC3b-th", [
            ("Explosive_Walker_(TCG)", 70),
            ("Infinity_Zone_(TCG)", 100),
            ("Legendary_Heartbeat_(TCG)", 76),
            ("Amazing_Volt_Tackle_(TCG)", 100),
            ("Shiny_Star_V_(TCG)", 190),  # S4a
        ]),
    ]:
        if sc_set not in by_set:
            continue
        cards = by_set[sc_set]
        print(f"\n{sc_set} ({len(cards)} missing): trying extra JA set sources...")

        # Build a combined name pool from all source sets
        combined_names: dict[str, str] = {}
        for page, total in extra_sources:
            names = fetch_en_names_from_combined_table(page, total)
            if names:
                combined_names.update(names)
                print(f"  {page}: {len(names)} names")
            time.sleep(0.5)

        # Also fetch ATCG page names if available
        atcg_pages = {
            "SC1a-th": [("Starter_Set_VMAX_(ATCG)", "A")],
            "SC1b-th": [("Starter_Set_VMAX_(ATCG)", "B")],
            "SC3a-th": [("Hidden_Shadow_(ATCG)", "A")],
            "SC3b-th": [("Hidden_Shadow_(ATCG)", "B")],
        }
        if sc_set in atcg_pages:
            for atcg_page, _ in atcg_pages[sc_set]:
                atcg_names = fetch_all_card_names_from_page(atcg_page)
                if atcg_names:
                    print(f"  ATCG {atcg_page}: {len(atcg_names)} names")
                    # These might directly match SC card numbers
                    matched = 0
                    for card in cards:
                        if card["id"] in [u[0] for u in updates]:
                            continue
                        en = atcg_names.get(card["number"])
                        if en:
                            updates.append((card["id"], en))
                            matched += 1
                    print(f"    Matched {matched} via ATCG page")

        # For remaining, the number mapping between SC and JA is unknown,
        # so we can't reliably match by number alone
        print(f"  Combined pool: {len(combined_names)} unique names")

    # ── SV secret rares: use extended numbering from Bulbapedia
    sv_extended = {
        "SV7s-th": ("Stellar_Miracle_(TCG)", 102),
        "SV8a-th": ("Terastal_Fest_ex_(TCG)", 187),
        "SV4a-th": ("Raging_Surf_(TCG)", 62),
        "SV11s-th": [],  # Page doesn't exist yet
    }

    for set_id, source in sv_extended.items():
        if set_id not in by_set:
            continue
        if not source:
            print(f"\n{set_id}: no source available, skipping")
            continue

        page, ja_total = source
        cards = by_set[set_id]
        print(f"\n{set_id} ({len(cards)} missing): {page} (extended /{ja_total:03d})...")

        name_map = fetch_en_names_from_combined_table(page, ja_total)
        if not name_map:
            # Try fetching all names from the page regardless of denominator
            name_map = fetch_all_card_names_from_page(page)

        if name_map:
            matched = 0
            for card in cards:
                en = name_map.get(card["number"]) or name_map.get(card["number"].lstrip("0") or "0")
                if en:
                    updates.append((card["id"], en))
                    matched += 1
            print(f"  Matched {matched}/{len(cards)}")
        else:
            print(f"  No names found")

        time.sleep(1)

    # ── MA sets: Thai-exclusive, try ATCG compilation pages
    ma_pages = {
        "MA1-th": "Premium_Set_(ATCG)",
        "MA2-th": "Premium_Set_2_(ATCG)",
        "MA3-th": "Premium_Set_3_(ATCG)",
        "MA4-th": "Premium_Set_4_(ATCG)",
    }

    for set_id, page in ma_pages.items():
        if set_id not in by_set:
            continue
        cards = by_set[set_id]
        print(f"\n{set_id} ({len(cards)} missing): trying {page}...")
        name_map = fetch_all_card_names_from_page(page)
        if name_map:
            matched = 0
            for card in cards:
                en = name_map.get(card["number"])
                if en:
                    updates.append((card["id"], en))
                    matched += 1
            print(f"  Matched {matched}/{len(cards)}")
        else:
            print(f"  Page not found or no names")
        time.sleep(1)

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
