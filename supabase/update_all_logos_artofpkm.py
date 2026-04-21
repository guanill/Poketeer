"""
update_all_logos_artofpkm.py — Scrape pack art thumbnails from artofpkm.com/cards
and update logo_url for all JA sets missing logos.

Uses direct artofpkm set ID → DB set ID mapping (no fuzzy name matching).

Run: python supabase/update_all_logos_artofpkm.py [--dry-run] [--all]
  --all    : also update sets that already have a logo
  --dry-run: show matches without updating DB
"""

import io
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")
sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
ARTOFPKM_BASE = "https://www.artofpkm.com"

# ---------------------------------------------------------------------------
# artofpkm numeric set ID → DB set ID
# IDs confirmed from https://www.artofpkm.com/cards
# ---------------------------------------------------------------------------
ARTOFPKM_ID_TO_SET_ID: dict[str, str] = {
    # PMCG era
    "6":   "PMCG1-ja",   # Base Set
    "8":   "PMCG2-ja",   # Pokémon Jungle
    "9":   "PMCG3-ja",   # The Secret of the Fossil
    "10":  "PMCG4-ja",   # Rocket Gang
    "18":  "PMCG5-ja",   # Gym Expansion 1: Gym Leader Stadiums
    "25":  "PMCG6-ja",   # Gym Expansion 2: Challenge from the Dark
    # Neo era
    "31":  "neo1-ja",    # Gold, Silver, to a New World...
    "34":  "neo2-ja",    # Crossing the Ruins...
    "40":  "neo3-ja",    # Awakening Legends
    "43":  "neo4-ja",    # Darkness, and to Light...
    "46":  "VS1-ja",     # Pokémon Card★VS
    "50":  "web1-ja",    # Pokémon Card★web
    # e-Card era
    "51":  "E1-ja",      # Base Expansion Pack
    "56":  "E2-ja",      # The Town on No Map
    "57":  "E3-ja",      # Wind from the Sea
    "59":  "E4-ja",      # Split Earth
    "61":  "E5-ja",      # Mysterious Mountains
    # ADV era
    "65":  "ADV1-ja",    # ADV Expansion Pack 1
    "71":  "ADV2-ja",    # Miracle of the Desert
    "73":  "ADV3-ja",    # Rulers of the Heavens
    "79":  "ADV4-ja",    # Magma VS Aqua: Two Ambitions
    "84":  "ADV5-ja",    # The Broken Seal
    # PCG era
    "88":  "PCG1-ja",    # Flight of Legends
    "91":  "PCG2-ja",    # Clash of the Blue Sky
    "100": "PCG3-ja",    # Rocket Gang Strikes Back
    "116": "PCG4-ja",    # Golden Sky, Silvery Ocean
    "117": "PCG5-ja",    # Mirage Forest
    "127": "PCG6-ja",    # Holon Research Tower
    "130": "PCG7-ja",    # Holon Phantom
    "134": "PCG8-ja",    # Miracle Crystal
    "137": "PCG9-ja",    # Offense and Defense of the Furthest Ends
    "119": "PCG10-ja",   # World Champions Pack
    # LEGEND era
    "203": "L1a-ja",     # HeartGold Collection
    "204": "L1b-ja",     # SoulSilver Collection
    "213": "L2-ja",      # Reviving Legends
    "217": "LL-ja",      # Lost Link
    "220": "L3-ja",      # Clash at the Summit
    # XY era
    "285": "XY1a-ja",    # Collection X
    "286": "XY1b-ja",    # Collection Y
    "290": "XY2-ja",     # Wild Blaze
    "294": "XY3-ja",     # Rising Fist
    "296": "XY4-ja",     # Phantom Gate
    "299": "XY5a-ja",    # Gaia Volcano
    "305": "XY6-ja",     # Emerald Break
    "308": "XY7-ja",     # Bandit Ring
    "521": "XY8a-ja",    # Blue Shock (Blue Impact)
    "522": "XY8b-ja",    # Red Flash
    "526": "XY9-ja",     # Rage of the Broken Heavens
    "528": "XY10-ja",    # Awakening Psychic King
    "537": "XY11a-ja",   # The Best of XY
    # CP sets
    "527": "CP3-ja",     # Pokékyun Collection
    "531": "CP4-ja",     # Premium Champion Pack EX x M x BREAK
    "534": "CP5-ja",     # Cruel Traitor
    "536": "CP6-ja",     # 20th Anniversary
    # SM era
    "323": "SM0-ja",     # Pikachu and their New Friends
    "325": "SM1S-ja",    # Collection Sun
    "326": "SM1M-ja",    # Collection Moon
    "332": "SM1+-ja",    # Sun & Moon
    "333": "SM2K-ja",    # Islands Await You
    "330": "SM2L-ja",    # Alolan Moonlight
    "335": "sm2+-ja",    # Beyond A New Challenge
    "341": "SM3+-ja",    # Shining Legend
    "339": "SM3H-ja",    # Did You See the Fighting Rainbow
    "338": "SM3N-ja",    # Light-Devouring Darkness
    "345": "SM4+-ja",    # GX Battle Boost
    "343": "SM4A-ja",    # Awakening Hero
    "342": "SM4S-ja",    # Ultra Dimensional Beast
    "352": "SM5+-ja",    # Ultra Forces
    "349": "SM5M-ja",    # Ultra Moon
    "350": "SM5S-ja",    # Ultra Sun
    "355": "SM6-ja",     # Forbidden Light
    "356": "SM6a-ja",    # Dragon Storm
    "357": "SM6b-ja",    # Champion Road
    "359": "SM7-ja",     # Sky-Splitting Charisma
    "360": "SM7a-ja",    # Thunderclap Spark
    "362": "SM7b-ja",    # Fairy Rise
    "364": "SM8-ja",     # Super Burst Impact
    "366": "SM8a-ja",    # Dark Order
    "368": "SM8b-ja",    # GX Ultra Shiny
    "372": "SM9-ja",     # Tag Bolt
    "373": "SM9a-ja",    # Night Unison
    "376": "SM9b-ja",    # Full Metal Wall
    "378": "SM10-ja",    # Double Blaze
    "383": "SM10b-ja",   # Sky Legend
    "381": "sn10a-ja",   # GG End
    "387": "SM11a-ja",   # Remix Bout
    "388": "SM11b-ja",   # Dream League
    "386": "sn11-ja",    # Miracle Twin
    "391": "SM12-ja",    # Alter Genesis
    "392": "SM12a-ja",   # Tag Team GX All Stars
    "382": "SMP2-ja",    # Detective Pikachu
    # SW&SH era
    "399": "S1H-ja",     # Shield
    "400": "S1W-ja",     # Sword
    "404": "S1a-ja",     # VMAX Rising
    "405": "S2-ja",      # Rebellion Crash
    "408": "S2a-ja",     # Explosive Walker
    "410": "S3-ja",      # Infinity Zone
    "411": "S3a-ja",     # Legendary Heartbeat
    "415": "S4-ja",      # Astonishing Volt Tackle
    "419": "S4a-ja",     # Shiny Star V
    "423": "S5R-ja",     # Rapid Strike Master
    "424": "S5I-ja",     # Single Strike Master
    "427": "S5a-ja",     # Matchless Fighters
    "429": "S6H-ja",     # Silver Lance
    "431": "S6K-ja",     # Jet-Black Poltergeist
    "432": "S6a-ja",     # Eevee Heroes
    "437": "S7R-ja",     # Blue Sky Stream
    "438": "S7D-ja",     # Skyscraping Perfect
    "442": "S8-ja",      # Fusion Arts
    "446": "S8a-ja",     # 25th Anniversary Collection
    "451": "S8b-ja",     # VMAX Climax
    "453": "S9-ja",      # Star Birth
    "456": "S9a-ja",     # Battle Region
    "459": "S10D-ja",    # Time Gazer
    "460": "S10P-ja",    # Space Juggler
    "462": "S10a-ja",    # Dark Fantasma
    "464": "S10b-ja",    # Pokémon GO
    "466": "S11-ja",     # Lost Abyss
    "473": "S11a-ja",    # Incandescent Arcana
    "476": "S12-ja",     # Paradigm Trigger
    "479": "S12a-ja",    # VSTAR Universe
    # SV era (main sets)
    "481": "SV1S-ja",    # Scarlet ex
    "482": "SV1V-ja",    # Violet ex
    "485": "SV1a-ja",    # Triplet Beat
    "484": "SV2P-ja",    # Snow Hazard
    "486": "SV2D-ja",    # Clay Burst
    "490": "SV2a-ja",    # Pokémon Card 151
    "493": "SV3-ja",     # Ruler of the Black Flame
    "502": "SV3a-ja",    # Raging Surf
    "501": "SV4K-ja",    # Ancient Roar
    "503": "SV4M-ja",    # Future Flash
    "506": "SV4a-ja",    # Shiny Treasure ex
    "508": "SV5K-ja",    # Wild Force
    "509": "SV5M-ja",    # Cyber Judge
    "513": "SV5a-ja",    # Crimson Haze
    "515": "SV6-ja",     # Mask of Change
    "519": "SV6a-ja",    # Night Wanderer
    "520": "SV7-ja",     # Stellar Miracle
    "544": "SV7a-ja",    # Paradise Dragona
    "551": "SV8-ja",     # Electric Breaker
    "552": "SV8a-ja",    # Terastal Festival ex
    "556": "SV9-ja",     # Battle Partners
    "557": "SV9a-ja",    # Hot Wind Arena
    "563": "SV10-ja",    # Glory of Team Rocket
    "565": "SV11B-ja",   # Black Bolt
    "566": "SV11W-ja",   # White Flare
    # CP sets (XY era supplementary)
    "301": "CP1-ja",     # Team Magma vs. Team Aqua Double Crisis
    "309": "CP2-ja",     # Legendary Holo Collection
    # SV special sets
    "542": "SVK-ja",     # Deck Build Box Stellar Miracle
    "549": "SVLN-ja",    # Starter Set Tera Type Stellar Sylveon ex
    "548": "SVLS-ja",    # Starter Set Tera Type Stellar Ceruledge ex
    # MEGA era
    "570": "M1-ja",      # Mega Brave
    "571": "M1S-ja",     # Mega Symphonia
    "575": "M2-ja",      # Inferno X
    "579": "M2pt5-ja",   # Mega Dream ex
    "583": "M3-ja",      # Nihil Zero
    "585": "M4-ja",      # Ninja Spinner
}


def fetch_artofpkm_sets() -> dict[str, dict]:
    """Fetch all sets from artofpkm /cards page. Returns {id: {name, data_src}}."""
    r = requests.get(f"{ARTOFPKM_BASE}/cards", headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text

    entries = re.findall(
        r'/sets/(\d+)"><div[^>]+><img alt="([^"]+)"[^>]+data-src="(/rails/active_storage/[^"]+)"',
        html,
    )
    return {e[0]: {"name": e[1], "data_src": e[2]} for e in entries}


def resolve_image_url(data_src: str) -> str | None:
    """Follow Active Storage redirect → CDN URL."""
    url = ARTOFPKM_BASE + data_src
    try:
        r = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
        return r.url if r.status_code == 200 else None
    except Exception as e:
        print(f"    Error: {e}")
        return None


def main():
    dry_run = "--dry-run" in sys.argv
    update_all = "--all" in sys.argv

    print("Fetching artofpkm set list...")
    aop_sets = fetch_artofpkm_sets()
    print(f"Found {len(aop_sets)} sets on artofpkm\n")

    # Get DB set logos
    db_sets = sb.table("sets").select("id, logo_url").eq("language", "ja").execute().data
    has_logo = {s["id"] for s in db_sets if s["logo_url"]}
    print(f"DB JA sets: {len(db_sets)}, already have logo: {len(has_logo)}\n")

    updated = 0
    skipped_has_logo = 0
    not_in_db = []

    for aop_id, set_id in sorted(ARTOFPKM_ID_TO_SET_ID.items(), key=lambda x: int(x[0])):
        if set_id in has_logo and not update_all:
            skipped_has_logo += 1
            continue

        aop_entry = aop_sets.get(aop_id)
        if not aop_entry:
            print(f"  ✗ artofpkm #{aop_id} not found on page (set: {set_id})")
            continue

        print(f"  {set_id}: artofpkm #{aop_id} '{aop_entry['name']}'")

        if not dry_run:
            img_url = resolve_image_url(aop_entry["data_src"])
            if img_url:
                sb.table("sets").update({"logo_url": img_url}).eq("id", set_id).execute()
                print(f"    → {img_url[:100]}")
                updated += 1
            else:
                print(f"    ✗ Could not resolve image")
            time.sleep(0.2)
        else:
            updated += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Updated: {updated} sets")
    print(f"Skipped (already have logo): {skipped_has_logo}")

    # Report DB sets still missing logos
    if not dry_run:
        remaining = sb.table("sets").select("id, name, logo_url").eq("language", "ja").execute().data
        missing = [s for s in remaining if not s["logo_url"]]
        if missing:
            print(f"\nDB sets still missing logos ({len(missing)}):")
            for s in missing:
                print(f"  {s['id']}: {s['name'][:50]}")
        else:
            print("\nAll JA sets now have logos!")


if __name__ == "__main__":
    main()
