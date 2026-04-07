"""
scrape_th_cards.py — Scrape ALL cards from Thai Pokémon TCG site and seed to Supabase.

Scrapes card data from https://asia.pokemon-card.com/th/card-search/
and upserts into the Supabase cards + sets tables.

Usage:
    pip install requests beautifulsoup4 supabase python-dotenv
    python supabase/scrape_th_cards.py
"""

import io
import json
import os
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
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.seed")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BATCH = 500

BASE_URL = "https://asia.pokemon-card.com/th"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})

# Thai sets from 2024-2025 with expansion codes
SETS_2024_2025 = {
    # 2025
    "MA4":  {"name": "Void Blast",                     "name_th": "วอยด์บลาสต์",                      "series": "Mega Evolution"},
    "MA3":  {"name": "Azure Blaze",                    "name_th": "อัคคีสีคราม",                       "series": "Mega Evolution"},
    "MA2":  {"name": "Mega Evolution Dream ex",        "name_th": "วิวัฒนาการเมก้า ดรีมex",            "series": "Mega Evolution"},
    "MA1":  {"name": "Mega Evolution",                 "name_th": "วิวัฒนาการเมก้า",                   "series": "Mega Evolution"},
    "SV10s":{"name": "Rise of the Undefeated",         "name_th": "การผงาดของผู้ไร้พ่าย",              "series": "Scarlet & Violet"},
    "SV9s": {"name": "Threads of Fate",                "name_th": "สายใยแห่งโชคชะตา",                  "series": "Scarlet & Violet"},
    "SV8a": {"name": "Terastal Festival ex",           "name_th": "เทศกาลเทรัสตัลex",                  "series": "Scarlet & Violet"},
    # 2024
    "SV8s": {"name": "Stellar Thunder",                "name_th": "สเตลลาร์สายฟ้าฟาด",                "series": "Scarlet & Violet"},
    "SV7s": {"name": "Stellar Guidance",               "name_th": "แสงนำทางแห่งสเตลลาร์",             "series": "Scarlet & Violet"},
    "SV6":  {"name": "Mask of Deception",              "name_th": "หน้ากากจอมลวงตา",                   "series": "Scarlet & Violet"},
    "SV5M": {"name": "Cyber Judge",                    "name_th": "ตุลาการไซเบอร์",                    "series": "Scarlet & Violet"},
    "SV5K": {"name": "Wild Force",                     "name_th": "ไวลด์ฟอร์ซ",                       "series": "Scarlet & Violet"},
    "SV5a": {"name": "Crimson Haze",                   "name_th": "คริมซัน เฮซ",                      "series": "Scarlet & Violet"},
    "SV4a": {"name": "Shiny Treasure ex",              "name_th": "ไชนีเทรเชอร์ex",                   "series": "Scarlet & Violet"},
    "SV4M": {"name": "Sparkle from the Future",        "name_th": "ประกายแสงจากอนาคต",                 "series": "Scarlet & Violet"},
    "SV4K": {"name": "Roar from the Past",             "name_th": "เสียงคำรามจากอดีต",                 "series": "Scarlet & Violet"},
}


def upsert_batch(table: str, rows: list[dict], batch_size: int = BATCH):
    total = len(rows)
    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        sb.table(table).upsert(batch).execute()
        done = min(i + batch_size, total)
        print(f"  {table}: {done}/{total}", end="\r")
    print(f"  {table}: {total}/{total} done")


def get_card_ids_for_set(expansion_code: str) -> list[int]:
    """Get all card detail IDs by crawling list pages."""
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
        links = soup.find_all("a", href=re.compile(r"/th/card-search/detail/(\d+)/"))
        page_ids = []
        for link in links:
            m = re.search(r"/detail/(\d+)/", link["href"])
            if m:
                page_ids.append(int(m.group(1)))

        if not page_ids:
            break

        card_ids.extend(page_ids)

        next_link = soup.find("a", href=re.compile(rf"pageNo={page + 1}"))
        if not next_link:
            break

        page += 1
        time.sleep(0.3)

    return list(dict.fromkeys(card_ids))


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

    # Extract card number like "J 001/123", "H 237/187", or "J 070/M-P"
    number_match = re.search(r"[A-Z]\s*(\d{1,4})\s*/\s*([A-Z0-9-]+)", text)
    if not number_match:
        return None

    number_str = f"{number_match.group(1)}/{number_match.group(2)}"
    # Strip leading zeros for the card number used in DB
    num_raw = number_match.group(1).lstrip("0") or "0"

    # Extract card name
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)

    # Image URL
    image_url = f"https://asia.pokemon-card.com/th/card-img/th{card_id:08d}.png"

    # Artist
    artist = ""
    illus_el = soup.find(string=re.compile(r"Illus\."))
    if illus_el:
        parent = illus_el.parent
        if parent:
            artist_text = parent.get_text(strip=True)
            m = re.search(r"Illus\.\s*(.+)", artist_text)
            if m:
                artist = m.group(1).strip()

    # HP
    hp = ""
    hp_match = re.search(r"HP\s*(\d+)", text)
    if hp_match:
        hp = hp_match.group(1)

    # Card type (Pokémon, Trainer, Energy)
    supertype = ""
    if "โปเกมอน" in text or hp:
        supertype = "Pokémon"
    elif "ซัพพอร์ต" in text or "サポート" in text or "Supporter" in text.lower():
        supertype = "Trainer"
    elif "ไอเท็ม" in text or "グッズ" in text or "Item" in text:
        supertype = "Trainer"
    elif "สเตเดียม" in text or "Stadium" in text.lower():
        supertype = "Trainer"
    elif "เอนเนอร์จี้" in text or "Energy" in text or "พลังงาน" in text:
        supertype = "Energy"

    return {
        "site_id": card_id,
        "name": name,
        "number": num_raw,
        "number_display": number_str,
        "image": image_url,
        "artist": artist,
        "hp": hp,
        "supertype": supertype,
    }


def main():
    print("=" * 60)
    print("Thai Pokemon TCG — Full Card Scraper (2024-2025)")
    print("=" * 60)

    all_set_rows: list[dict] = []
    all_card_rows: list[dict] = []

    for exp_code, info in SETS_2024_2025.items():
        set_id = f"{exp_code}-th"
        print(f"\n[{exp_code}] {info['name']} ({info['name_th']})")
        print(f"  Fetching card list...")

        card_ids = get_card_ids_for_set(exp_code)
        print(f"  Found {len(card_ids)} cards, fetching details...")

        if not card_ids:
            continue

        # Build set row
        all_set_rows.append({
            "id": set_id,
            "name": info["name_th"],
            "series": info["series"],
            "printed_total": len(card_ids),
            "total": len(card_ids),
            "release_date": "",
            "language": "th",
            "symbol_url": "",
            "logo_url": "",
        })

        # Fetch card details with thread pool
        cards = []
        errors = 0
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
                cards.append(result)
                time.sleep(0.05)

        cards.sort(key=lambda c: c["site_id"])
        print(f"  Fetched: {len(cards)}, Errors: {errors}          ")

        # Build card rows for Supabase
        seen_ids = set()
        for c in cards:
            card_key = f"{exp_code}-{c['number']}-th"
            # Handle duplicate numbers within the same set (alt arts etc.)
            if card_key in seen_ids:
                card_key = f"{exp_code}-{c['number']}-{c['site_id']}-th"
            seen_ids.add(card_key)
            all_card_rows.append({
                "id": card_key,
                "name": c["name"],
                "number": c["number"],
                "set_id": set_id,
                "rarity": "",
                "image_small": c["image"],
                "image_large": c["image"],
                "supertype": c["supertype"],
                "subtypes": [],
                "hp": c["hp"],
                "artist": c["artist"],
                "types": [],
                "name_en": "",
            })

    # Upsert to Supabase
    print(f"\n{'=' * 60}")
    print(f"TOTALS: {len(all_set_rows)} sets, {len(all_card_rows)} cards")
    print(f"{'=' * 60}")

    if all_set_rows:
        print("\nUpserting sets...")
        upsert_batch("sets", all_set_rows)

    if all_card_rows:
        print("Upserting cards...")
        upsert_batch("cards", all_card_rows)

    # Also save a local JSON backup
    output_path = ROOT / "backend" / "th_cards_2024_2025.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_card_rows, f, ensure_ascii=False, indent=2)
    print(f"\nLocal backup saved to {output_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
