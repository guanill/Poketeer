"""
fill_images_artofpkm.py — Fill missing JA card images from artofpkm.com.

Cards on artofpkm are listed in numerical order, matching our DB card ordering.
We scrape image URLs, follow redirects to stable CDN URLs, then match by position.

Usage:
    python supabase/fill_images_artofpkm.py             # all mapped sets with missing images
    python supabase/fill_images_artofpkm.py --set M3-ja # single set
    python supabase/fill_images_artofpkm.py --all       # all mapped sets regardless
"""

import io
import os
import re
import sys
import time
from html.parser import HTMLParser
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

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 poketeer-bot"

# Map: our DB set_id → artofpkm /sets/{id}
SET_MAP = {
    # MEGA era
    "M4-ja":    585,  # Ninja Spinner
    "M3-ja":    583,  # Nihil Zero / ムニキスゼロ
    "M2pt5-ja": 579,  # Mega Dream ex
    "M2-ja":    575,  # Inferno X
    "M1S-ja":   571,  # Mega Symphonia / メガシンフォニア
    "M1-ja":    570,  # Mega Brave
    # SV era
    "SV11W-ja": 566,  # White Flare
    "SV11B-ja": 565,  # Black Bolt
    "SV10-ja":  563,  # Glory of Team Rocket
    "SV9a-ja":  557,  # Hot Wind Arena
    "SV9-ja":   556,  # Battle Partners
    "SV8a-ja":  552,  # Terastal Festival ex
    "SV8-ja":   551,  # Electric Breaker
    "SV7a-ja":  544,  # Paradise Dragona
    "SV7-ja":   520,  # Stellar Miracle
    "SV6a-ja":  519,  # Night Wanderer
    "SV6-ja":   515,  # Mask of Change
    "SV5a-ja":  513,  # Crimson Haze
    "SV5K-ja":  508,  # Wild Force
    "SV5M-ja":  509,  # Cyber Judge
    "SV4a-ja":  506,  # Shiny Treasure ex
    "SV4K-ja":  501,  # Ancient Roar
    "SV4M-ja":  503,  # Future Flash
    "SV3a-ja":  502,  # Raging Surf
    "SV3-ja":   493,  # Ruler of the Black Flame
    "SV2a-ja":  490,  # Pokémon Card 151
    "SV2D-ja":  486,  # Clay Burst
    "SV2P-ja":  484,  # Snow Hazard
    "SV1a-ja":  485,  # Triplet Beat
    "SV1V-ja":  482,  # Violet ex
    "SV1S-ja":  481,  # Scarlet ex
}


BASE = "https://www.artofpkm.com"


def extract_card_entries(html: str) -> dict[int, str]:
    """Extract {artofpkm_card_number: active_storage_url} from lightbox data attrs."""
    # data-lightbox-url="/sets/N/card/CARDNUM" ... href="/rails/active_storage/..."
    matches = re.findall(
        r'data-lightbox-url="/sets/\d+/card/(\d+)"[^>]*href="(/rails/active_storage/[^"]+)"',
        html,
    )
    return {int(num): BASE + href for num, href in matches}


def scrape_set_images(artofpkm_id: int) -> dict[int, str]:
    """Return {artofpkm_card_number: cdn_url} for all cards in a set."""
    card_map: dict[int, str] = {}

    # First page (~100 cards)
    r = SESSION.get(f"{BASE}/sets/{artofpkm_id}", timeout=30)
    r.raise_for_status()
    card_map.update(extract_card_entries(r.text))

    # Subsequent batches via turbo-frame infinite scroll
    offset = 100
    while True:
        r = SESSION.get(f"{BASE}/sets/{artofpkm_id}/card_batches?offset={offset}", timeout=30)
        r.raise_for_status()
        batch = extract_card_entries(r.text)
        if not batch:
            break
        card_map.update(batch)
        offset += 100
        time.sleep(0.1)

    print(f"  Found {len(card_map)} card entries (artofpkm numbers {min(card_map)}-{max(card_map)})")

    # Follow redirects to stable CDN URLs
    cdn_map: dict[int, str] = {}
    for card_num, active_url in sorted(card_map.items()):
        try:
            redir = SESSION.get(active_url, allow_redirects=False, timeout=10)
            cdn = redir.headers.get("location", "")
            cdn_map[card_num] = cdn if cdn else active_url
        except Exception:
            cdn_map[card_num] = active_url
        time.sleep(0.03)

    return cdn_map


def get_db_cards(set_id: str) -> list[dict]:
    """Get cards for a set ordered by card ID (zero-padded, so numeric order is correct)."""
    res = sb.table("cards").select("id,number,image_small").eq("set_id", set_id).order("id").execute()
    return res.data or []


def count_missing(set_id: str) -> int:
    res = (sb.table("cards").select("id", count="exact")
           .eq("set_id", set_id)
           .or_("image_small.is.null,image_small.eq.").execute())
    return res.count or 0


def process_set(set_id: str, artofpkm_id: int, force: bool = False) -> None:
    missing = count_missing(set_id)
    if missing == 0 and not force:
        print(f"  {set_id}: all images present, skipping")
        return

    print(f"\n{set_id} (artofpkm/{artofpkm_id}) — {missing} missing images")
    print(f"  Scraping images...")
    try:
        cdn_map = scrape_set_images(artofpkm_id)
    except Exception as e:
        print(f"  ERROR scraping: {e}")
        return

    cards = get_db_cards(set_id)
    print(f"  artofpkm: {len(cdn_map)} images | DB: {len(cards)} cards")

    if not cdn_map:
        print(f"  No images found, skipping")
        return

    updated = 0
    skipped = 0
    no_entry = 0
    # artofpkm numbers cards 1..N matching DB number ordering
    for i, card in enumerate(cards):
        artofpkm_num = i + 1  # artofpkm uses 1-based sequential numbering
        img_url = cdn_map.get(artofpkm_num)
        if not img_url:
            no_entry += 1
            continue
        if card.get("image_small") and not force:
            skipped += 1
            continue
        sb.table("cards").update({
            "image_small": img_url,
            "image_large": img_url,
        }).eq("id", card["id"]).execute()
        updated += 1

    print(f"  Updated: {updated} | Skipped: {skipped} | No artofpkm entry: {no_entry}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", help="Only process this set (e.g. M3-ja)")
    ap.add_argument("--all", action="store_true", help="Process all sets (even with images)")
    args = ap.parse_args()

    target_sets = SET_MAP
    if args.set:
        if args.set not in SET_MAP:
            print(f"ERROR: {args.set} not in SET_MAP")
            sys.exit(1)
        target_sets = {args.set: SET_MAP[args.set]}

    print(f"Processing {len(target_sets)} set(s)...")
    for set_id, artofpkm_id in target_sets.items():
        process_set(set_id, artofpkm_id, force=args.all)

    print("\nAll done!")


if __name__ == "__main__":
    main()
