"""
Add English names to Japanese set names in the format:
  "日本語名 (English Name)"
to match the Thai set naming convention.
"""

import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Mapping: set_id → English name
# Sources: Bulbapedia, pokemon-tcg wiki, official EN set equivalents
JA_EN_NAMES = {
    # ── Scarlet & Violet era ──
    "SV1S-ja": "Scarlet ex",
    "SV1V-ja": "Violet ex",
    "sv1a-ja": "Triplet Beat",
    "SV1a-ja": "Triplet Beat",
    "SV2P-ja": "Snow Hazard",
    "SV2D-ja": "Clay Burst",
    "SV2a-ja": "Pokémon Card 151",
    "SV3-ja": "Ruler of the Black Flame",
    "SV3a-ja": "Raging Surf",
    "SV4a-ja": "Raging Surf",
    "SV4K-ja": "Ancient Roar",
    "SV4M-ja": "Future Flash",
    "SV5K-ja": "Wild Force",
    "SV5M-ja": "Cyber Judge",
    "SV5a-ja": "Crimson Haze",
    "SV6-ja": "Mask of Change",
    "SV6a-ja": "Night Wanderer",
    "SV7-ja": "Stellar Miracle",
    "SV7a-ja": "Paradise Dragona",
    "SV8-ja": "Super Electric Breaker",
    "SV8a-ja": "Terastal Fest ex",
    "SV9-ja": "Battle Partners",
    "SV9a-ja": "Arena of Hot Wind",
    "SV10-ja": "Team Rocket's Glory",
    "SV11W-ja": "White Flare",
    "SVK-ja": "Deck Build BOX Stellar Miracle",
    "SVLN-ja": "Starter Set Tera Type: Stellar Sylveon ex",
    "SVLS-ja": "Starter Set Tera Type: Stellar Ceruledge ex",

    # ── Sword & Shield era (S) ──
    "S1W-ja": "Sword",
    "S1H-ja": "Shield",
    "S1a-ja": "VMAX Rising",
    "s1a-ja": "VMAX Rising",
    "S2-ja": "Rebellion Crash",
    "S2a-ja": "Explosive Walker",
    "S3-ja": "Infinity Zone",
    "S3a-ja": "Legendary Heartbeat",
    "S4-ja": "Astonishing Volt Tackle",
    "S4a-ja": "Shiny Star V",
    "S5I-ja": "Single Strike Master",
    "S5R-ja": "Rapid Strike Master",
    "S5a-ja": "Matchless Fighters",
    "S6K-ja": "Jet-Black Poltergeist",
    "S6H-ja": "Silver Lance",
    "S6a-ja": "Eevee Heroes",
    "S7R-ja": "Blue Sky Stream",
    "S7D-ja": "Skyscraping Perfection",
    "S8-ja": "Fusion Arts",
    "S8a-ja": "25th Anniversary Collection",
    "S8b-ja": "VMAX Climax",
    "S9-ja": "Star Birth",
    "S9a-ja": "Battle Region",
    "S10P-ja": "Space Juggler",
    "S10D-ja": "Time Gazer",
    "S10a-ja": "Dark Phantasma",
    "S10b-ja": "Pokémon GO",
    "S11-ja": "Lost Abyss",
    "S11a-ja": "Incandescent Arcana",
    "S12-ja": "Paradigm Trigger",
    "S12a-ja": "VSTAR Universe",

    # ── Sun & Moon era (SM) ──
    "SM0-ja": "Pikachu and New Friends",
    "SM1S-ja": "Collection Sun",
    "SM1M-ja": "Collection Moon",
    "SM1+-ja": "Sun & Moon",
    "SM2L-ja": "Alolan Moonlight",
    "SM2K-ja": "Islands Await You",
    "SM3N-ja": "Darkness that Consumes Light",
    "SM3H-ja": "To Have Seen the Battle Rainbow",
    "SM3+-ja": "Shining Legends",
    "SM4S-ja": "Awakened Heroes",
    "SM4A-ja": "Ultra Dimension Beasts",
    "SM4+-ja": "GX Battle Boost",
    "SM5S-ja": "Ultra Sun",
    "SM5M-ja": "Ultra Moon",
    "SM5+-ja": "Ultra Force",
    "SM6-ja": "Forbidden Light",
    "SM6a-ja": "Dragon Storm",
    "SM6b-ja": "Champion Road",
    "SM7-ja": "Charisma of the Wrecked Sky",
    "SM7a-ja": "Thunderclap Spark",
    "SM7b-ja": "Fairy Rise",
    "SM8-ja": "Super Burst Impact",
    "SM8a-ja": "Dark Order",
    "SM8b-ja": "GX Ultra Shiny",
    "SM9-ja": "Tag Bolt",
    "SM9a-ja": "Night Unison",
    "SM9b-ja": "Full Metal Wall",
    "sn10a-ja": "GG End",
    "sn11-ja": "Miracle Twin",
    "SMP2-ja": "Detective Pikachu",
    "SM10-ja": "Double Blaze",
    "SM10b-ja": "Sky Legend",
    "SM11a-ja": "Remix Bout",
    "SM11b-ja": "Dream League",
    "SM12-ja": "Alter Genesis",
    "SM12a-ja": "TAG TEAM GX Tag All Stars",

    # ── XY era ──
    "XY1a-ja": "Collection X",
    "XY1b-ja": "Collection Y",
    "XY2-ja": "Wild Blaze",
    "XY3-ja": "Rising Fist",
    "XY4-ja": "Phantom Gate",
    "XY5a-ja": "Tidal Storm",
    "XY6-ja": "Emerald Break",
    "XY7-ja": "Bandit Ring",
    "XY8a-ja": "Blue Shock",
    "XY8b-ja": "Red Flash",
    "XY9-ja": "Rage of the Broken Heavens",
    "XY10-ja": "Awakening Psychic King",
    "XY11a-ja": "Cruel Traitor",

    # ── BW/Classic/Legend era ──
    "L1a-ja": "HeartGold Collection",
    "L1b-ja": "SoulSilver Collection",
    "L2-ja": "Reviving Legends",
    "L3-ja": "Clash at the Summit",
    "LL-ja": "Lost Link",

    # ── ADV era ──
    "ADV1-ja": "Expansion Pack",
    "ADV2-ja": "Miracle of the Desert",
    "ADV3-ja": "Rulers of the Heavens",
    "ADV4-ja": "Magma vs Aqua: Two Ambitions",
    "ADV5-ja": "Undone Seal",

    # ── PCG era ──
    "PCG1-ja": "Flight of Legends",
    "PCG2-ja": "Clash of the Blue Sky",
    "PCG3-ja": "Rocket Gang Strikes Back",
    "PCG4-ja": "Golden Sky, Silvery Ocean",
    "PCG5-ja": "Mirage Forest",
    "PCG6-ja": "Holon Research Tower",
    "PCG7-ja": "Holon Phantom",
    "PCG8-ja": "Miracle Crystal",
    "PCG9-ja": "Offense and Defense of the Furthest Ends",
    "PCG10-ja": "World Champions Pack",

    # ── E-Card era ──
    "E1-ja": "Base Expansion Pack",
    "E2-ja": "The Town on No Map",
    "E3-ja": "Wind from the Sea",
    "E4-ja": "Split Earth",
    "E5-ja": "Mysterious Mountains",

    # ── Neo era ──
    "neo1-ja": "Gold, Silver, to a New World...",
    "neo2-ja": "Crossing the Ruins...",
    "neo3-ja": "Awakening Legends",
    "neo4-ja": "Darkness, and to Light...",

    # ── Classic PMCG ──
    "PMCG1-ja": "Expansion Pack",
    "PMCG2-ja": "Pokémon Jungle",
    "PMCG3-ja": "Fossil",
    "PMCG4-ja": "Team Rocket",
    "PMCG5-ja": "Leaders' Stadium",
    "PMCG6-ja": "Challenge from the Darkness",

    # ── Special sets ──
    "VS1-ja": "Pokémon Card VS",
    "web1-ja": "Pokémon Card Web",
    "CP1-ja": "Magma vs Aqua Double Crisis",
    "CP2-ja": "Legendary Shine Collection",
    "CP3-ja": "Poké Kyun Collection",
    "CP4-ja": "Premium Champion Pack EX×M×BREAK",
    "CP5-ja": "Cruel Traitor",
    "CP6-ja": "Expansion Pack 20th Anniversary",

    # ── CS (Chinese Simplified) sets that appear as JA ──
    "CS1.5-ja": "Triplet Beat",
    "CS1a-ja": "Triplet Beat",
    "CS1b-ja": "Triplet Beat",
    "CS2.5-ja": "Triplet Beat",
    "CS2a-ja": "Triplet Beat",
    "CS2b-ja": "Triplet Beat",
    "CS3.5-ja": "Triplet Beat",
}


def main():
    # Fetch all JA sets
    result = sb.table("sets").select("id, name").like("id", "%-ja").execute()
    sets = result.data or []
    print(f"Found {len(sets)} JA sets\n")

    updated = 0
    skipped = 0
    missing = []

    for s in sets:
        sid = s["id"]
        name = s["name"]

        # Skip if already has English name in parentheses
        if "(" in name and ")" in name:
            skipped += 1
            continue

        en_name = JA_EN_NAMES.get(sid)
        if not en_name:
            missing.append(f"  {sid}: {name}")
            continue

        new_name = f"{name} ({en_name})"
        sb.table("sets").update({"name": new_name}).eq("id", sid).execute()
        print(f"  OK {sid}: {new_name}")
        updated += 1

    print(f"\nDone: {updated} updated, {skipped} already had English names")
    if missing:
        print(f"\n{len(missing)} sets without English mapping:")
        for m in missing:
            print(m)


if __name__ == "__main__":
    main()
