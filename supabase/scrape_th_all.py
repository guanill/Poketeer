"""
scrape_th_all.py — Scrape ALL Thai Pokemon TCG cards and sets from
https://asia.pokemon-card.com/th/card-search/

Discovers all sets automatically from the site, scrapes every card,
and upserts everything to Supabase.

Usage:
    pip install requests beautifulsoup4 supabase python-dotenv
    python supabase/scrape_th_all.py
"""

import io
import json
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
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.seed")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
BATCH = 500

BASE_URL = "https://asia.pokemon-card.com/th"
IMG_BASE = f"{BASE_URL}/card-img/products"
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


# ─── Step 1: Discover all sets from the search page ────────────────────────

def discover_sets() -> list[dict]:
    """Scrape all set pages to discover sets with their expansion codes, names, dates, and images."""
    sets = []
    seen_codes = set()

    for page_num in range(1, 10):
        url = f"{BASE_URL}/card-search/?pageNo={page_num}"
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception:
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find all product links that have expansionCodes
        links = soup.find_all("a", href=re.compile(r"expansionCodes="))
        if not links:
            break

        for link in links:
            href = link.get("href", "")
            code_match = re.search(r"expansionCodes=([^&]+)", href)
            if not code_match:
                continue

            exp_code = code_match.group(1)
            if exp_code in seen_codes:
                continue
            seen_codes.add(exp_code)

            # Get set name from link text
            name = link.get_text(strip=True)
            # Clean up prefix like "การ์ดชุดเสริม" etc.
            name = re.sub(r'^การ์ดชุดเสริม(ไฮคลาส|เพิ่มความแกร่ง)?\s*', '', name)
            name = name.strip('"').strip()

            # Get image from nearby img tag
            img = link.find("img")
            img_url = ""
            if img and img.get("src"):
                img_url = img["src"]
                if not img_url.startswith("http"):
                    img_url = f"https://asia.pokemon-card.com{img_url}"

            # Get release date from nearby text
            parent = link.parent
            date_text = parent.get_text(" ", strip=True) if parent else ""
            date_match = re.search(r"(\d{2})-(\d{2})-(\d{4})", date_text)
            release_date = ""
            if date_match:
                release_date = f"{date_match.group(3)}-{date_match.group(1)}-{date_match.group(2)}"

            sets.append({
                "code": exp_code,
                "name": name,
                "release_date": release_date,
                "logo_url": img_url,
            })

        # Check for next page
        next_link = soup.find("a", href=re.compile(rf"pageNo={page_num + 1}"))
        if not next_link:
            break

        time.sleep(0.5)

    return sets


# ─── Step 2: Get card IDs for a set ───────────────────────────────────────

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


# ─── Step 3: Fetch card detail ────────────────────────────────────────────

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


# ─── English name mapping ────────────────────────────────────────────────

# Map of known Thai names → English names for set display
EN_NAMES = {
    "วอยด์บลาสต์": "Void Blast",
    "วิวัฒนาการเมก้า ดรีมex": "Mega Evolution Dream ex",
    "อัคคีสีคราม": "Azure Blaze",
    "วิวัฒนาการเมก้า": "Mega Evolution",
    "แบล็ก & ไวท์": "Black & White",
    "การผงาดของผู้ไร้พ่าย": "Rise of the Undefeated",
    "สายใยแห่งโชคชะตา": "Threads of Fate",
    "เทศกาลเทรัสตัลex": "Terastal Festival ex",
    "สเตลลาร์สายฟ้าฟาด": "Stellar Thunder",
    "แสงนำทางแห่งสเตลลาร์": "Stellar Guidance",
    "หน้ากากจอมลวงตา": "Mask of Deception",
    "หมอกสีชาด": "Crimson Haze",
    "อำนาจอนารยะ": "Wild Force",
    "ตุลาการไซเบอร์": "Cyber Judge",
    "ไชนีเทรเชอร์ex": "Shiny Treasure ex",
    "ประกายแสงจากอนาคต": "Sparkle from the Future",
    "เสียงคำรามจากอดีต": "Roar from the Past",
    "ราชาแห่งเพลิงกาฬ": "Ruler of the Black Flame",
    "คลื่นพิโรธ": "Raging Surf",
    "โปเกมอนการ์ด 151": "Pokemon Card 151",
    "สโนว์ฮาซาร์ด": "Snow Hazard",
    "เคลย์เบิสต์": "Clay Burst",
    "ทริปเปิลบีต": "Triple Beat",
    "สการ์เล็ต ex": "Scarlet ex",
    "ไวโอเล็ต ex": "Violet ex",
    "จักรวาลแห่ง VSTAR": "VSTAR Universe",
    "ปฐมบทแห่งยุคใหม่": "Paradigm Trigger",
    "อาร์คานาแห่งประกายแสง": "Incandescent Arcana",
    "ลอสต์เวิลด์": "Lost Abyss",
    "อันธการลวงตา": "Dark Phantasma",
    "เจ้าแห่งกาลเวลา": "Time Gazer",
    "จอมมายาผ่ามิติ": "Space Juggler",
    "พสุธามหายุทธ": "Battle Region",
    "สตาร์เบิร์ท": "Star Birth",
    "VMAX ไคลแมกซ์": "VMAX Climax",
    "จู่โจมแบบฟิวชัน": "Fusion Arts",
    "เพอร์เฟคระฟ้า": "Blue Sky Stream",
    "สายน้ำแห่งนภา": "Skyscraping Perfection",
    "อีวุยฮีโร": "Eevee Heroes",
    "หอกหิมะขาว": "Silver Lance",
    "ภูตทมิฬ": "Jet Black Poltergeist",
    "สองยอดนักสู้": "Matchless Fighters",
    "มาสเตอร์จู่โจมครั้งเดียว": "Single Strike Master",
    "มาสเตอร์จู่โจมต่อเนื่อง": "Rapid Strike Master",
    "คริมซัน เฮซ": "Crimson Haze",
}


def add_english_suffix(thai_name: str) -> str:
    """If we know the English name, append it in parentheses."""
    for th, en in EN_NAMES.items():
        if th in thai_name:
            if f"({en})" not in thai_name:
                return f"{thai_name} ({en})"
            return thai_name
    return thai_name


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Thai Pokemon TCG — Full Site Scraper")
    print("=" * 60)

    # Discover sets
    print("\nDiscovering sets from search pages...")
    discovered = discover_sets()
    print(f"  Found {len(discovered)} sets\n")

    # Check which sets we already have
    existing = sb.table("sets").select("id").like("id", "%-th").execute()
    existing_ids = {r["id"] for r in (existing.data or [])}
    print(f"  Already in DB: {len(existing_ids)} sets")

    all_set_rows: list[dict] = []
    all_card_rows: list[dict] = []

    for i, s in enumerate(discovered):
        set_id = f"{s['code']}-th"
        display_name = add_english_suffix(s["name"])

        print(f"\n[{i+1}/{len(discovered)}] {s['code']}: {display_name}")

        # Determine series
        series = "Scarlet & Violet"
        if s["code"].startswith("S") and not s["code"].startswith("SV"):
            series = "Sword & Shield"
        elif s["code"].startswith("MA"):
            series = "Mega Evolution"

        # Always get card count for the set
        card_ids = get_card_ids(s["code"])
        print(f"  Cards: {len(card_ids)}")

        # Build set row
        all_set_rows.append({
            "id": set_id,
            "name": display_name,
            "series": series,
            "printed_total": len(card_ids),
            "total": len(card_ids),
            "release_date": s["release_date"],
            "language": "th",
            "symbol_url": "",
            "logo_url": s["logo_url"],
        })

        # Skip card scraping if already in DB (just update the set metadata)
        if set_id in existing_ids:
            print(f"  Cards already in DB, skipping detail scrape")
            continue

        if not card_ids:
            continue

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
            card_key = f"{s['code']}-{c['number']}-th"
            if card_key in seen_ids:
                card_key = f"{s['code']}-{c['number']}-{c['site_id']}-th"
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

    # Upsert
    print(f"\n{'=' * 60}")
    print(f"TOTALS: {len(all_set_rows)} sets, {len(all_card_rows)} new cards")
    print(f"{'=' * 60}")

    if all_set_rows:
        print("\nUpserting sets (metadata + pack images)...")
        upsert_batch("sets", all_set_rows)

    if all_card_rows:
        print("Upserting cards...")
        upsert_batch("cards", all_card_rows)

    print("\nDone!")


if __name__ == "__main__":
    main()
