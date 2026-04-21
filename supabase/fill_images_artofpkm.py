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
    # PMCG era
    "PMCG1-ja": 6,    # Base Set
    "PMCG2-ja": 8,    # Pokémon Jungle
    "PMCG3-ja": 9,    # The Secret of the Fossil
    "PMCG4-ja": 10,   # Rocket Gang
    "PMCG5-ja": 18,   # Gym Expansion 1
    "PMCG6-ja": 25,   # Gym Expansion 2
    # Neo era
    "neo1-ja":  31,   # Gold, Silver, to a New World...
    "neo2-ja":  34,   # Crossing the Ruins...
    "neo3-ja":  40,   # Awakening Legends
    "neo4-ja":  43,   # Darkness, and to Light...
    "VS1-ja":   46,   # Pokémon Card★VS
    "web1-ja":  50,   # Pokémon Card★web
    # e-Card era
    "E1-ja":    51,   # Base Expansion Pack
    "E2-ja":    56,   # The Town on No Map
    "E3-ja":    57,   # Wind from the Sea
    "E4-ja":    59,   # Split Earth
    "E5-ja":    61,   # Mysterious Mountains
    # ADV era
    "ADV1-ja":  65,   # ADV Expansion Pack 1
    "ADV2-ja":  71,   # Miracle of the Desert
    "ADV3-ja":  73,   # Rulers of the Heavens
    "ADV4-ja":  79,   # Magma VS Aqua: Two Ambitions
    "ADV5-ja":  84,   # The Broken Seal
    # PCG era
    "PCG1-ja":  88,   # Flight of Legends
    "PCG2-ja":  91,   # Clash of the Blue Sky
    "PCG3-ja":  100,  # Rocket Gang Strikes Back
    "PCG4-ja":  116,  # Golden Sky, Silvery Ocean
    "PCG5-ja":  117,  # Mirage Forest
    "PCG6-ja":  127,  # Holon Research Tower
    "PCG7-ja":  130,  # Holon Phantom
    "PCG8-ja":  134,  # Miracle Crystal
    "PCG9-ja":  137,  # Offense and Defense of the Furthest Ends
    "PCG10-ja": 119,  # World Champions Pack
    # LEGEND era
    "L1a-ja":   203,  # HeartGold Collection
    "L1b-ja":   204,  # SoulSilver Collection
    "L2-ja":    213,  # Reviving Legends
    "LL-ja":    217,  # Lost Link
    "L3-ja":    220,  # Clash at the Summit
    # XY era
    "XY1a-ja":  285,  # Collection X
    "XY1b-ja":  286,  # Collection Y
    "XY2-ja":   290,  # Wild Blaze
    "XY3-ja":   294,  # Rising Fist
    "XY4-ja":   296,  # Phantom Gate
    "XY5a-ja":  299,  # Gaia Volcano
    "CP1-ja":   301,  # Double Crisis
    "XY6-ja":   305,  # Emerald Break
    "XY7-ja":   308,  # Bandit Ring
    "CP2-ja":   309,  # Legendary Holo Collection
    "XY8a-ja":  521,  # Blue Shock
    "XY8b-ja":  522,  # Red Flash
    "XY9-ja":   526,  # Rage of the Broken Heavens
    "CP3-ja":   527,  # Pokékyun Collection
    "XY10-ja":  528,  # Awakening Psychic King
    "CP4-ja":   531,  # Premium Champion Pack
    "CP5-ja":   534,  # Cruel Traitor
    "CP6-ja":   536,  # 20th Anniversary
    # SM era
    "SM0-ja":   323,  # Pikachu and their New Friends
    "SM1S-ja":  325,  # Collection Sun
    "SM1M-ja":  326,  # Collection Moon
    "SM1+-ja":  332,  # Sun & Moon
    "SM2K-ja":  333,  # Islands Await You
    "SM2L-ja":  330,  # Alolan Moonlight
    "sm2+-ja":  335,  # Beyond A New Challenge
    "SM3+-ja":  341,  # Shining Legend
    "SM3H-ja":  339,  # Did You See the Fighting Rainbow
    "SM3N-ja":  338,  # Light-Devouring Darkness
    "SM4+-ja":  345,  # GX Battle Boost
    "SM4A-ja":  343,  # Awakening Hero
    "SM4S-ja":  342,  # Ultra Dimensional Beast
    "SM5+-ja":  352,  # Ultra Forces
    "SM5M-ja":  349,  # Ultra Moon
    "SM5S-ja":  350,  # Ultra Sun
    "SM6-ja":   355,  # Forbidden Light
    "SM6a-ja":  356,  # Dragon Storm
    "SM6b-ja":  357,  # Champion Road
    "SM7-ja":   359,  # Sky-Splitting Charisma
    "SM7a-ja":  360,  # Thunderclap Spark
    "SM7b-ja":  362,  # Fairy Rise
    "SM8-ja":   364,  # Super Burst Impact
    "SM8a-ja":  366,  # Dark Order
    "SM8b-ja":  368,  # GX Ultra Shiny
    "SM9-ja":   372,  # Tag Bolt
    "SM9a-ja":  373,  # Night Unison
    "SM9b-ja":  376,  # Full Metal Wall
    "SM10-ja":  378,  # Double Blaze
    "sn10a-ja": 381,  # GG End
    "SMP2-ja":  382,  # Detective Pikachu
    "SM10b-ja": 383,  # Sky Legend
    "sn11-ja":  386,  # Miracle Twin
    "SM11a-ja": 387,  # Remix Bout
    "SM11b-ja": 388,  # Dream League
    "SM12-ja":  391,  # Alter Genesis
    "SM12a-ja": 392,  # Tag Team GX All Stars
    # SW&SH era
    "S1H-ja":   399,  # Shield
    "S1W-ja":   400,  # Sword
    "S1a-ja":   404,  # VMAX Rising
    "S2-ja":    405,  # Rebellion Crash
    "S2a-ja":   408,  # Explosive Walker
    "S3-ja":    410,  # Infinity Zone
    "S3a-ja":   411,  # Legendary Heartbeat
    "S4-ja":    415,  # Astonishing Volt Tackle
    "S4a-ja":   419,  # Shiny Star V
    "S5R-ja":   423,  # Rapid Strike Master
    "S5I-ja":   424,  # Single Strike Master
    "S5a-ja":   427,  # Matchless Fighters
    "S6H-ja":   429,  # Silver Lance
    "S6K-ja":   431,  # Jet-Black Poltergeist
    "S6a-ja":   432,  # Eevee Heroes
    "S7R-ja":   437,  # Blue Sky Stream
    "S7D-ja":   438,  # Skyscraping Perfect
    "S8-ja":    442,  # Fusion Arts
    "S8a-ja":   446,  # 25th Anniversary Collection
    "S8b-ja":   451,  # VMAX Climax
    "S9-ja":    453,  # Star Birth
    "S9a-ja":   456,  # Battle Region
    "S10D-ja":  459,  # Time Gazer
    "S10P-ja":  460,  # Space Juggler
    "S10a-ja":  462,  # Dark Fantasma
    "S10b-ja":  464,  # Pokémon GO
    "S11-ja":   466,  # Lost Abyss
    "S11a-ja":  473,  # Incandescent Arcana
    "S12-ja":   476,  # Paradigm Trigger
    "S12a-ja":  479,  # VSTAR Universe
    # SV era
    "SV1S-ja":  481,  # Scarlet ex
    "SV1V-ja":  482,  # Violet ex
    "SV1a-ja":  485,  # Triplet Beat
    "SV2P-ja":  484,  # Snow Hazard
    "SV2D-ja":  486,  # Clay Burst
    "SV2a-ja":  490,  # Pokémon Card 151
    "SV3-ja":   493,  # Ruler of the Black Flame
    "SV3a-ja":  502,  # Raging Surf
    "SV4K-ja":  501,  # Ancient Roar
    "SV4M-ja":  503,  # Future Flash
    "SV4a-ja":  506,  # Shiny Treasure ex
    "SV5K-ja":  508,  # Wild Force
    "SV5M-ja":  509,  # Cyber Judge
    "SV5a-ja":  513,  # Crimson Haze
    "SV6-ja":   515,  # Mask of Change
    "SV6a-ja":  519,  # Night Wanderer
    "SV7-ja":   520,  # Stellar Miracle
    "SV7a-ja":  544,  # Paradise Dragona
    "SV8-ja":   551,  # Electric Breaker
    "SV8a-ja":  552,  # Terastal Festival ex
    "SV9-ja":   556,  # Battle Partners
    "SV9a-ja":  557,  # Hot Wind Arena
    "SV10-ja":  563,  # Glory of Team Rocket
    "SV11B-ja": 565,  # Black Bolt
    "SV11W-ja": 566,  # White Flare
    # MEGA era
    "M1-ja":    570,  # Mega Brave
    "M1S-ja":   571,  # Mega Symphonia
    "M2-ja":    575,  # Inferno X
    "M2pt5-ja": 579,  # Mega Dream ex
    "M3-ja":    583,  # Nihil Zero
    "M4-ja":    585,  # Ninja Spinner
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
