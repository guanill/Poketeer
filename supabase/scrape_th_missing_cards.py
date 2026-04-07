"""
scrape_th_missing_cards.py — Scrape cards for Thai sets that have
set metadata but no cards in the database.

Reuses the card detail scraping from scrape_th_all.py.
Only scrapes booster pack sets that have searchable cards.
"""

import io
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BATCH = 500

BASE_URL = "https://asia.pokemon-card.com/th"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})


def upsert_batch(table: str, rows: list[dict]):
    total = len(rows)
    for i in range(0, total, BATCH):
        batch = rows[i : i + BATCH]
        sb.table(table).upsert(batch).execute()
        done = min(i + BATCH, total)
        print(f"  {table}: {done}/{total}", end="\r")
    print(f"  {table}: {total}/{total} done")


def get_card_ids(exp_code: str) -> list[int]:
    card_ids = []
    page = 1
    while True:
        url = f"{BASE_URL}/card-search/list/?expansionCodes={exp_code}&pageNo={page}"
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception:
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
        time.sleep(0.2)
    return list(dict.fromkeys(card_ids))


def fetch_card_detail(card_id: int) -> dict | None:
    url = f"{BASE_URL}/card-search/detail/{card_id}/"
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    number_match = re.search(r"[A-Z]\s*(\d{1,4})\s*/\s*([A-Z0-9-]+)", text)
    if not number_match:
        return None

    num_raw = number_match.group(1).lstrip("0") or "0"

    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)

    image_url = f"https://asia.pokemon-card.com/th/card-img/th{card_id:08d}.png"

    artist = ""
    illus_el = soup.find(string=re.compile(r"Illus\."))
    if illus_el and illus_el.parent:
        m = re.search(r"Illus\.\s*(.+)", illus_el.parent.get_text(strip=True))
        if m:
            artist = m.group(1).strip()

    hp = ""
    hp_match = re.search(r"HP\s*(\d+)", text)
    if hp_match:
        hp = hp_match.group(1)

    supertype = ""
    if hp:
        supertype = "Pokémon"
    elif any(w in text for w in ["ซัพพอร์ต", "ไอเท็ม", "สเตเดียม", "Supporter", "Item", "Stadium"]):
        supertype = "Trainer"
    elif any(w in text for w in ["เอนเนอร์จี้", "พลังงาน", "Energy"]):
        supertype = "Energy"

    return {
        "site_id": card_id,
        "name": name,
        "number": num_raw,
        "image": image_url,
        "artist": artist,
        "hp": hp,
        "supertype": supertype,
    }


def main():
    print("=" * 60)
    print("Scraping cards for Thai sets with missing cards")
    print("=" * 60)

    # Sets that have searchable cards on the site
    SETS_TO_SCRAPE = [
        "SC1a", "SC1b", "SC3a", "SC3b",
        "S5I", "S5R", "S5a", "S6H", "S6K", "S6a", "S7D", "S7R",
        "S8", "S8a", "S8b", "S9", "S9a",
        "S10D", "S10P", "S10a", "S10b", "S11", "S11a",
        "SV1a",
    ]

    all_card_rows: list[dict] = []

    for i, code in enumerate(SETS_TO_SCRAPE):
        set_id = f"{code}-th"

        # Check if set already has cards
        existing = sb.table("cards").select("id", count="exact", head=True).eq("set_id", set_id).execute()
        if (existing.count or 0) > 0:
            print(f"[{i+1}/{len(SETS_TO_SCRAPE)}] {code}: already has {existing.count} cards, skipping")
            continue

        print(f"\n[{i+1}/{len(SETS_TO_SCRAPE)}] {code}: fetching card IDs...")
        card_ids = get_card_ids(code)
        print(f"  Found {len(card_ids)} card IDs")

        if not card_ids:
            continue

        # Update set total if needed
        sb.table("sets").update({
            "printed_total": len(card_ids),
            "total": len(card_ids),
        }).eq("id", set_id).execute()

        # Fetch card details
        print(f"  Fetching card details...")
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
                time.sleep(0.03)

        cards.sort(key=lambda c: c["site_id"])
        print(f"  Fetched: {len(cards)}, Errors: {errors}          ")

        seen_ids = set()
        for c in cards:
            card_key = f"{code}-{c['number']}-th"
            if card_key in seen_ids:
                card_key = f"{code}-{c['number']}-{c['site_id']}-th"
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

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {len(all_card_rows)} new cards to upsert")
    print(f"{'=' * 60}")

    if all_card_rows:
        print("\nUpserting cards...")
        upsert_batch("cards", all_card_rows)

    print("\nDone!")


if __name__ == "__main__":
    main()
