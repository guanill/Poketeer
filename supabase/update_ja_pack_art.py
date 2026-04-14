"""
update_ja_pack_art.py — Set pack foil images for Japanese sets from pokemon-card.com.

Uses the product images on pokemon-card.com/ex/{code}/ which are transparent RGBA PNGs
showing the actual booster pack foil, not the promotional hero art.

Usage:
    python supabase/update_ja_pack_art.py
    python supabase/update_ja_pack_art.py --force   # overwrite existing logos
"""

import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE = "https://www.pokemon-card.com/ex"

# DB set ID prefix → full pack foil image URL from pokemon-card.com
# All images are RGBA transparent PNGs showing the actual booster pack.
SET_PACK_MAP = {
    # SV era
    "SV1S":  f"{BASE}/sv1/assets/images/hero-visual.jpg",    # Scarlet ex
    "SV1V":  f"{BASE}/sv1/assets/images/hero-visual.jpg",    # Violet ex
    "SV1a":  f"{BASE}/sv1/assets/images/hero-visual.jpg",    # Triplet Beat (shared page)
    "SV2a":  f"{BASE}/sv2a/assets/images/product-image-1.png",  # Pokémon Card 151
    "SV2P":  f"{BASE}/sv2a/assets/images/product-image-2.png",  # Snow Hazard
    "SV2D":  f"{BASE}/sv2a/assets/images/product-image-3.png",  # Clay Burst
    "SV3":   f"{BASE}/sv3/assets/images/product-image-1.png",   # Ruler of the Black Flame
    "SV3a":  f"{BASE}/sv3/assets/images/product-image-2.png",   # Raging Surf
    "SV4K":  f"{BASE}/sv4/assets/images/product-image-1.png",   # Ancient Roar
    "SV4M":  f"{BASE}/sv4/assets/images/product-image-2.png",   # Future Flash
    "SV4a":  f"{BASE}/sv4a/assets/images/product-image-1.png",  # Shiny Treasure ex
    "SV5K":  f"{BASE}/sv5/assets/images/product-image-1.png",   # Wild Force
    "SV5M":  f"{BASE}/sv5/assets/images/product-image-2.png",   # Cyber Judge
    "SV5a":  f"{BASE}/sv5/assets/images/hero-visual.jpg",       # Crimson Haze (no own page)
    "SV6":   f"{BASE}/sv6/assets/images/product-image-1.png",   # Mask of Change
    "SV6a":  f"{BASE}/sv6/assets/images/hero-visual.jpg",       # Night Wanderer (no own page)
    "SV7":   f"{BASE}/sv7/assets/images/product-image-1.png",   # Stellar Miracle
    "SV7a":  f"{BASE}/sv7/assets/images/product-image-2.png",   # Paradise Dragona
    "SV8":   f"{BASE}/sv8/assets/images/product-image-1.png",   # Electric Breaker
    "SV8a":  f"{BASE}/sv8a/assets/images/product-image-1.png",  # Terastal Festival ex
    "SV9":   f"{BASE}/sv9/assets/images/product-slide1-1.png",  # Battle Partners
    "SV9a":  f"{BASE}/sv9/assets/images/product-slide2-1.png",  # Hot Wind Arena
    "SV10":  f"{BASE}/sv10/assets/images/infoProduct-img-1.png",# Glory of Team Rocket
    "SV11B": f"{BASE}/sv11/assets/images/infoProduct-img-1.png",# Black Bolt
    "SV11W": f"{BASE}/sv11/assets/images/infoProduct-img-2.png",# White Flare
    # MEGA era
    "M1":    f"{BASE}/m1/assets/images/product-img-1.png",      # Mega Brave
    "M1S":   f"{BASE}/m1/assets/images/product-img-2.png",      # Mega Symphonia
    "M2":    f"{BASE}/m2/assets/images/product-img-01.png",     # Inferno X
    "M2pt5": f"{BASE}/m2a/assets/images/product-img-01.png",    # MEGA Dream ex
    "M3":    f"{BASE}/m3/assets/images/product-img-01.png",     # Nihil Zero
    "M4":    f"{BASE}/m4/assets/images/product-img-01-4gmgu.png", # Ninja Spinner
}


def check_url(url: str) -> bool:
    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Overwrite existing logos")
    args = ap.parse_args()

    print("Updating Japanese set pack foil images from pokemon-card.com...\n")

    res = sb.table("sets").select("id, name, logo_url").like("id", "%-ja").execute()
    ja_sets = {r["id"]: r for r in (res.data or [])}
    print(f"  JA sets in DB: {len(ja_sets)}")

    updated = 0
    skipped = 0
    failed = 0

    for set_code, image_url in SET_PACK_MAP.items():
        set_id = f"{set_code}-ja"
        if set_id not in ja_sets:
            continue

        current = ja_sets[set_id]
        if current.get("logo_url") and not args.force:
            print(f"  {set_id}: already has logo, skipping (use --force to overwrite)")
            skipped += 1
            continue

        if not check_url(image_url):
            print(f"  {set_id}: URL not available — {image_url}")
            failed += 1
            continue

        sb.table("sets").update({"logo_url": image_url}).eq("id", set_id).execute()
        print(f"  {set_id} ({current['name']}): updated")
        updated += 1

    print(f"\nDone! Updated: {updated}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
