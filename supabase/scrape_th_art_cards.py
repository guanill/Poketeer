"""
scrape_th_art_cards.py — Scrape art/secret rare cards from the Thai Pokémon TCG site.

Art cards are identified by having a card number higher than the set total
(e.g. 237/187 is a secret rare because 237 > 187).

Scrapes: https://asia.pokemon-card.com/th/card-search/

Usage:
    pip install requests beautifulsoup4
    python supabase/scrape_th_art_cards.py
"""

import io
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Fix Windows console encoding for Thai characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://asia.pokemon-card.com/th"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})

# Thai sets released in 2024-2025 (expansion codes from the site)
# Sourced from https://asia.pokemon-card.com/th/card-search/ product listing
SETS_2024_2025 = {
    # 2025
    "MA4":  "วอยด์บลาสต์ (Void Blast)",
    "MA3":  "อัคคีสีคราม (Azure Blaze)",
    "MA2":  "วิวัฒนาการเมก้า ดรีมex (Mega Evolution Dream ex)",
    "MA1":  "วิวัฒนาการเมก้า (Mega Evolution)",
    "SV10s": "การผงาดของผู้ไร้พ่าย (Rise of the Undefeated)",
    "SV9s": "สายใยแห่งโชคชะตา (Threads of Fate)",
    "SV8a": "เทศกาลเทรัสตัลex (Terastal Festival ex)",
    # 2024
    "SV8s": "สเตลลาร์สายฟ้าฟาด (Stellar Thunder)",
    "SV7s": "แสงนำทางแห่งสเตลลาร์ (Stellar Guidance)",
    "SV6":  "หน้ากากจอมลวงตา (Mask of Deception)",
    "SV5M": "ตุลาการไซเบอร์ (Cyber Judge)",
    "SV5K": "ไวลด์ฟอร์ซ (Wild Force)",
    "SV5a": "คริมซัน เฮซ (Crimson Haze)",
    "SV4a": "ไชนีเทรเชอร์ex (Shiny Treasure ex)",
    "SV4M": "ประกายแสงจากอนาคต (Sparkle from the Future)",
    "SV4K": "เสียงคำรามจากอดีต (Roar from the Past)",
}


def get_card_ids_for_set(expansion_code: str) -> list[int]:
    """Get all card detail IDs for a given expansion code by crawling list pages."""
    card_ids = []
    page = 1

    while True:
        url = f"{BASE_URL}/card-search/list/?expansionCodes={expansion_code}&pageNo={page}"
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"    Error fetching page {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find all card detail links like /th/card-search/detail/12345/
        links = soup.find_all("a", href=re.compile(r"/th/card-search/detail/(\d+)/"))
        page_ids = []
        for link in links:
            m = re.search(r"/detail/(\d+)/", link["href"])
            if m:
                page_ids.append(int(m.group(1)))

        if not page_ids:
            break

        card_ids.extend(page_ids)

        # Check if there's a next page
        next_link = soup.find("a", href=re.compile(rf"pageNo={page + 1}"))
        if not next_link:
            break

        page += 1
        time.sleep(0.3)

    return list(dict.fromkeys(card_ids))  # dedupe preserving order


def fetch_card_detail(card_id: int) -> dict | None:
    """Fetch a single card's detail page and extract data."""
    url = f"{BASE_URL}/card-search/detail/{card_id}/"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Extract card number like "J 001/123" or "H 237/187"
    number_match = re.search(r"[A-Z]\s*(\d{1,4})\s*/\s*(\d{1,4})", text)
    if not number_match:
        return None

    card_num = int(number_match.group(1))
    set_total = int(number_match.group(2))
    number_str = f"{number_match.group(1)}/{number_match.group(2)}"

    # Extract card name (usually in h1 or the first big text)
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)

    # Extract image
    image_url = f"https://asia.pokemon-card.com/th/card-img/th{card_id:08d}.png"

    # Try to find artist
    artist = ""
    artist_match = re.search(r"(?:Illus\.|Artist|วาดภาพ)[:\s]*([^\n]+)", text)
    if not artist_match:
        # Look for common artist patterns in img alt text or specific elements
        illus_el = soup.find(string=re.compile(r"Illus\."))
        if illus_el:
            # The artist name is usually nearby
            parent = illus_el.parent
            if parent:
                artist_text = parent.get_text(strip=True)
                artist_match2 = re.search(r"Illus\.\s*(.+)", artist_text)
                if artist_match2:
                    artist = artist_match2.group(1).strip()
    else:
        artist = artist_match.group(1).strip()

    # Extract HP
    hp = ""
    hp_match = re.search(r"HP\s*(\d+)", text)
    if hp_match:
        hp = hp_match.group(1)

    return {
        "site_id": card_id,
        "name": name,
        "number": number_str,
        "card_num": card_num,
        "set_total": set_total,
        "is_art": card_num > set_total,
        "image": image_url,
        "artist": artist,
        "hp": hp,
    }


def main():
    print("=" * 60)
    print("Thai Pokémon TCG — Art Card Scraper (2024-2025)")
    print("=" * 60)

    all_art_cards: list[dict] = []

    for exp_code, set_name in SETS_2024_2025.items():
        print(f"\n[{exp_code}] {set_name}")
        print(f"  Fetching card list...")

        card_ids = get_card_ids_for_set(exp_code)
        print(f"  Found {len(card_ids)} cards")

        if not card_ids:
            continue

        set_art_cards = []
        errors = 0

        # Fetch card details with thread pool (4 workers to be polite)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_card_detail, cid): cid for cid in card_ids}

            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                if done_count % 20 == 0:
                    print(f"  Progress: {done_count}/{len(card_ids)}", end="\r")

                result = future.result()
                if result is None:
                    errors += 1
                    continue

                if result["is_art"]:
                    result["set_code"] = exp_code
                    result["set_name"] = set_name
                    set_art_cards.append(result)

                time.sleep(0.05)

        set_art_cards.sort(key=lambda c: c["card_num"])
        all_art_cards.extend(set_art_cards)

        print(f"  Art cards: {len(set_art_cards)}, Errors: {errors}")
        for c in set_art_cards:
            print(f"    #{c['number']:>10s}  {c['name']}  (by {c['artist'] or '?'})")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"TOTAL ART CARDS FOUND: {len(all_art_cards)}")
    print(f"{'=' * 60}")

    # Group by set
    by_set: dict[str, list] = {}
    for c in all_art_cards:
        by_set.setdefault(c["set_code"], []).append(c)

    for code, cards in by_set.items():
        name = SETS_2024_2025.get(code, code)
        print(f"\n  {code} — {name} ({len(cards)} art cards):")
        for c in cards:
            print(f"    #{c['number']:>10s}  {c['name']}  (by {c['artist'] or '?'})")

    # Save to JSON
    output_path = ROOT / "backend" / "art_cards_th_2024_2025.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean up internal fields before saving
    export = []
    for c in all_art_cards:
        export.append({
            "id": c["site_id"],
            "name": c["name"],
            "number": c["number"],
            "set_code": c["set_code"],
            "set_name": c["set_name"],
            "image": c["image"],
            "artist": c["artist"],
            "hp": c["hp"],
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
