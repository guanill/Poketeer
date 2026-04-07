"""
fill_th_en_names_bulba.py — Fill English names for Thai cards using
Bulbapedia expansion pages.

Each JA set (S6H, S8, etc.) maps to an EN expansion (Chilling Reign,
Fusion Strike, etc.) on Bulbapedia. The EN page's "Set lists" table
contains rows with both EN numbering (001/198) and JA numbering (001/070).
We extract the JA number + EN card name to build a mapping.
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

# Map TH set code -> (Bulbapedia page name, JA total cards for /NNN pattern)
# Thai sets use the same codes as JA sets
TH_SET_TO_BULBA: dict[str, list[tuple[str, int]]] = {
    # Sword & Shield era
    "SC1a": [("Sword_(TCG)", 60)],        # S1W Sword
    "SC1b": [("Shield_(TCG)", 60)],        # S1H Shield
    "SC3a": [("Infinity_Zone_(TCG)", 100)], # S3 Infinity Zone
    "SC3b": [("Legendary_Heartbeat_(TCG)", 76)],  # S3a Legendary Heartbeat
    "S6H":  [("Silver_Lance_(TCG)", 70)],
    "S6K":  [("Jet-Black_Spirit_(TCG)", 70)],
    "S6a":  [("Eevee_Heroes_(TCG)", 69)],
    "S7D":  [("Skyscraping_Perfection_(TCG)", 67)],
    "S7R":  [("Blue_Sky_Stream_(TCG)", 67)],
    "S8":   [("Fusion_Arts_(TCG)", 100)],
    "S8a":  [("25th_Anniversary_Collection_(TCG)", 28)],
    "S8b":  [("VMAX_Climax_(TCG)", 184)],
    "S9":   [("Star_Birth_(TCG)", 100)],
    "S9a":  [("Battle_Region_(TCG)", 67)],
    "S10D": [("Time_Gazer_(TCG)", 67)],
    "S10P": [("Space_Juggler_(TCG)", 67)],
    "S10a": [("Dark_Phantasma_(TCG)", 71)],
    "S10b": [("Pokémon_GO_(TCG)", 71)],
    "S11":  [("Lost_Abyss_(TCG)", 100)],
    "S11a": [("Incandescent_Arcana_(TCG)", 68)],
    "S12a": [("VSTAR_Universe_(TCG)", 172)],
    # SV era
    "SV1a": [("Triplet_Beat_(TCG)", 73)],
    "SV7s": [("Stellar_Miracle_(TCG)", 102)],
    "SV11s": [("Supercharged_Breaker_(TCG)", 100)],  # Might not exist yet
    # MA sets are Thai-only, try matching via Bulbapedia ATCG pages
    "MA1":  [("Master_Ball_Mirror_(TCG)", 0)],  # May not exist
    "MA2":  [("Master_Ball_Mirror_(TCG)", 0)],
    "MA3":  [("Master_Ball_Mirror_(TCG)", 0)],
    "MA4":  [("Master_Ball_Mirror_(TCG)", 0)],
}


def fetch_bulba_card_names(page: str, ja_total: int) -> dict[str, str]:
    """
    Fetch card names from a Bulbapedia expansion page.
    Returns {number: english_name} for the JA set (using /NNN pattern).
    """
    url = f"{BULBA}/wiki/{page}"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Error fetching {url}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    name_map: dict[str, str] = {}

    if ja_total == 0:
        return {}

    # Pattern to match JA card numbers like "001/070"
    ja_pattern = re.compile(rf"(\d{{3}})/{ja_total:03d}")

    # Find all tables on the page
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if f"/{ja_total:03d}" not in text:
            continue

        # Parse rows
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue

            # Check each cell for JA number
            row_text = ""
            for cell in cells:
                row_text += " " + cell.get_text(strip=True)

            ja_match = ja_pattern.search(row_text)
            if not ja_match:
                continue

            num = ja_match.group(1).lstrip("0") or "0"

            # Find the card name - it's usually in a cell with an <a> tag
            name = ""
            for cell in cells:
                # Look for links that are likely card names (not images, not categories)
                for link in cell.find_all("a"):
                    href = link.get("href", "")
                    link_text = link.get_text(strip=True)
                    # Skip non-card links
                    if not link_text or len(link_text) < 2:
                        continue
                    if "/wiki/" not in href:
                        continue
                    if any(skip in href.lower() for skip in ["file:", "category:", "type)", "special:"]):
                        continue
                    if link_text in ("Promotion", "Promo"):
                        continue
                    # Skip rarity text
                    if link_text in ("Common", "Uncommon", "Rare", "Holo", "Ultra", "Secret"):
                        continue
                    # This is likely the card name
                    name = link_text
                    break
                if name:
                    break

            if name and num not in name_map:
                # Clean up the name - remove "(TCG)" suffix if present
                name = re.sub(r"\s*\(TCG\)\s*$", "", name)
                name_map[num] = name

    return name_map


def main():
    print("=" * 60)
    print("Filling Thai card English names from Bulbapedia")
    print("=" * 60)

    # Get TH cards still missing name_en
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

    print(f"Found {len(all_missing)} TH cards missing name_en\n")

    # Group by set
    by_set: dict[str, list[dict]] = {}
    for card in all_missing:
        by_set.setdefault(card["set_id"], []).append(card)

    updates: list[tuple[str, str]] = []

    for set_id in sorted(by_set):
        code = set_id.replace("-th", "")
        cards = by_set[set_id]

        if code not in TH_SET_TO_BULBA:
            print(f"{set_id} ({len(cards)} cards): no Bulbapedia mapping, skipping")
            continue

        for page, ja_total in TH_SET_TO_BULBA[code]:
            if ja_total == 0:
                print(f"{set_id} ({len(cards)} cards): no JA total known, skipping")
                continue

            print(f"{set_id} ({len(cards)} cards): fetching from {page} (/{ja_total:03d})...")
            name_map = fetch_bulba_card_names(page, ja_total)

            if not name_map:
                print(f"  No card names found")
                continue

            matched = 0
            for card in cards:
                num = card["number"]
                en = (
                    name_map.get(num)
                    or name_map.get(num.lstrip("0") or "0")
                    or name_map.get(num.zfill(3))
                )
                if en:
                    updates.append((card["id"], en))
                    matched += 1

            print(f"  Matched {matched}/{len(cards)} cards")

        time.sleep(1)  # Be nice to Bulbapedia

    print(f"\n{'=' * 60}")
    print(f"Total updates: {len(updates)}")
    print(f"{'=' * 60}")

    if updates:
        print("\nApplying updates...")
        for i, (card_id, name_en) in enumerate(updates):
            sb.table("cards").update({"name_en": name_en}).eq("id", card_id).execute()
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(updates)}", end="\r")
        print(f"  {len(updates)}/{len(updates)} done")

    # Final count
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
