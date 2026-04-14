"""
add_perfect_order.py — Seed the "Perfect Order" (me3) English set from pokemontcg.io.
"""

import io
import os
import sys
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

SET_ID = "me3"
API = "https://api.pokemontcg.io/v2"


def main():
    print(f"Fetching set {SET_ID} from pokemontcg.io...")
    set_resp = requests.get(f"{API}/sets/{SET_ID}", timeout=30)
    set_resp.raise_for_status()
    s = set_resp.json()["data"]

    set_row = {
        "id": s["id"],
        "name": s["name"],
        "series": s.get("series", ""),
        "printed_total": s.get("printedTotal", 0),
        "total": s.get("total", 0),
        "release_date": s.get("releaseDate", ""),
        "language": "en",
        "logo_url": s.get("images", {}).get("logo", ""),
        "symbol_url": s.get("images", {}).get("symbol", ""),
    }
    print(f"  {set_row['name']} ({set_row['total']} cards, released {set_row['release_date']})")

    print("Upserting set...")
    sb.table("sets").upsert(set_row).execute()

    print(f"Fetching cards for {SET_ID}...")
    cards = []
    page = 1
    while True:
        resp = requests.get(
            f"{API}/cards",
            params={"q": f"set.id:{SET_ID}", "page": page, "pageSize": 250},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        cards.extend(data["data"])
        if len(data["data"]) < 250:
            break
        page += 1

    print(f"  Fetched {len(cards)} cards")

    rows = []
    for c in cards:
        images = c.get("images", {})
        rows.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "number": c.get("number", ""),
            "set_id": SET_ID,
            "rarity": c.get("rarity", "") or "",
            "image_small": images.get("small", ""),
            "image_large": images.get("large", ""),
            "supertype": c.get("supertype", "") or "",
            "subtypes": c.get("subtypes", []) or [],
            "hp": str(c.get("hp", "")) if c.get("hp") else "",
            "artist": c.get("artist", "") or "",
            "types": c.get("types", []) or [],
            "name_en": c.get("name", ""),
        })

    print(f"Upserting {len(rows)} cards...")
    for i in range(0, len(rows), 200):
        batch = rows[i : i + 200]
        sb.table("cards").upsert(batch).execute()
        print(f"  {min(i + 200, len(rows))}/{len(rows)}", end="\r")
    print()

    print("Done!")


if __name__ == "__main__":
    main()
