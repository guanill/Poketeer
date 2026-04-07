"""
fill_ja_set_images.py — Fetch pack artwork images for Japanese sets from
pokemon-card.com products API.
"""

import io
import os
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

BASE = "https://www.pokemon-card.com"


def main():
    print("=" * 60)
    print("Fetching Japanese set pack art from pokemon-card.com")
    print("=" * 60)

    # Get all JA sets
    ja_sets = sb.table("sets").select("id, name, logo_url").eq("language", "ja").execute()
    needs_logo = {s["id"]: s["name"] for s in ja_sets.data if not s.get("logo_url")}
    print(f"JA sets needing logo: {len(needs_logo)}\n")

    # Build case-insensitive lookup: lowercase code -> set ID
    code_lookup: dict[str, str] = {}
    for s in ja_sets.data:
        code = s["id"].replace("-ja", "")
        code_lookup[code.lower()] = s["id"]

    # Fetch all expansion products from API
    print("Fetching products from API...")
    all_products = []
    for page in range(1, 11):
        url = f"{BASE}/products/resultAPI.php?productType=expansion&page={page}"
        r = session.get(url, timeout=15)
        data = r.json()
        all_products.extend(data.get("products", []))
        if page >= data.get("maxPage", 10):
            break
    print(f"Found {len(all_products)} products\n")

    updates: dict[str, str] = {}  # set_id -> image_url

    for p in all_products:
        img = p.get("tumbsImg", "")
        title = p.get("productTitle", "")
        detail = p.get("link_detailPage", "")

        if "デラックス" in title:
            continue
        if not img:
            continue

        full_img = BASE + img if img.startswith("/") else img
        filename = img.split("/")[-1].lower()

        # Strategy 1: Extract code from detail URL
        code_match = re.search(r"/(?:ex|products/\w+)/([a-zA-Z0-9]+)", detail)
        if code_match:
            raw_code = code_match.group(1).lower()
            if raw_code in code_lookup:
                set_id = code_lookup[raw_code]
                if set_id in needs_logo and set_id not in updates:
                    updates[set_id] = full_img

        # Strategy 2: Extract code from image filename
        for pattern in [
            r"(sv\d+[a-z]?)[\._]",
            r"(s\d+[a-z]?)[\._]",
            r"(sm\d+[a-z+]?)[\._]",
            r"(sm\d+[a-z+]?)pillow",
            r"(\d+_sm\d+[a-z+]?)_",
            r"(m\d+[a-z]?)(?:pkg|\.|_)",
        ]:
            m = re.search(pattern, filename, re.I)
            if m:
                raw = m.group(1)
                # Remove leading numbers like "1322_SM5m" -> "SM5m"
                raw = re.sub(r"^\d+_", "", raw)
                code = raw.lower()
                if code in code_lookup:
                    set_id = code_lookup[code]
                    if set_id in needs_logo and set_id not in updates:
                        updates[set_id] = full_img
                break

        # Strategy 3: Match specific paired set codes from filename
        # sv11b -> SV11B, sv11w -> SV11W, ichigeki -> S5I, rengeki -> S5R
        special_map = {
            "sv11b": "SV11B-ja",
            "sv11w": "SV11W-ja",
            "ichigeki": "S5I-ja",
            "rengeki": "S5R-ja",
            "sv5_21": "SV5K-ja",   # Wild Force
            "sv5_20": "SV5M-ja",   # Cyber Judge
            "sv4k": "SV4K-ja",
            "sv4m": "SV4M-ja",
            "sv2p": "SV2P-ja",
            "sv2d": "SV2D-ja",
            "sv1s": "SV1S-ja",
            "sv1v": "SV1V-ja",
            "s10d": "S10D-ja",
            "s10p": "S10P-ja",
            "s7d": "S7D-ja",
            "s7r": "S7R-ja",
            "s6h": "S6H-ja",
            "s5i": "S5I-ja",
            "s5r": "S5R-ja",
            "sm1-s": "SM1S-ja",
            "sm1-m": "SM1M-ja",
            "sm7": "SM7-ja",
        }

        for key, set_id in special_map.items():
            if key in filename.lower():
                if set_id in needs_logo and set_id not in updates:
                    updates[set_id] = full_img
                break

    # Apply updates
    print(f"Matched {len(updates)} sets to images\n")
    for set_id, img_url in sorted(updates.items()):
        name = needs_logo.get(set_id, "")
        print(f"  {set_id:15s} | {name[:25]:25s} | {img_url}")
        sb.table("sets").update({"logo_url": img_url}).eq("id", set_id).execute()

    # Check remaining
    still = sum(1 for s in ja_sets.data if not s.get("logo_url") and s["id"] not in updates)
    print(f"\nUpdated: {len(updates)}")
    print(f"Still without logo: {still}")
    print("Done!")


if __name__ == "__main__":
    main()
