"""
update_set_metadata.py — Fix series (English), release dates, and name_en for JA sets.

Usage:
    python supabase/update_set_metadata.py
"""

import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))

# id → (name_en, series, release_date)
# series: English era name shown in UI
# release_date: YYYY-MM-DD confirmed from official sources
SET_METADATA: dict[str, tuple[str, str, str]] = {
    # Original PMCG (Pocket Monsters Card Game)
    "PMCG1-ja": ("Base Set",             "Pocket Monsters Card Game", "1996-10-20"),
    "PMCG2-ja": ("Jungle",               "Pocket Monsters Card Game", "1997-03-05"),
    "PMCG3-ja": ("Fossil",               "Pocket Monsters Card Game", "1997-06-21"),
    "PMCG4-ja": ("Rocket Gang",          "Pocket Monsters Card Game", "1997-11-21"),
    "PMCG5-ja": ("Gym Heroes",           "Pocket Monsters Card Game", "1998-10-24"),
    "PMCG6-ja": ("Gym Challenge",        "Pocket Monsters Card Game", "1999-06-25"),
    # Neo
    "neo1-ja":  ("Neo Genesis",          "Neo",                       "2000-02-04"),
    "neo2-ja":  ("Neo Discovery",        "Neo",                       "2000-07-07"),
    "neo3-ja":  ("Neo Revelation",       "Neo",                       "2000-11-23"),
    "neo4-ja":  ("Neo Destiny",          "Neo",                       "2001-04-20"),
    "VS1-ja":   ("VS",                   "VS",                        "2001-07-19"),
    "web1-ja":  ("Web",                  "Web",                       "2001-10-20"),
    # e-Series
    "E1-ja":    ("Base Expansion Pack",  "e-Card",                    "2001-12-01"),
    "E2-ja":    ("Town on No Map",       "e-Card",                    "2002-03-08"),
    "E3-ja":    ("Wind from the Sea",    "e-Card",                    "2002-05-24"),
    "E4-ja":    ("Split Earth",          "e-Card",                    "2002-08-23"),
    "E5-ja":    ("Mysterious Mountains", "e-Card",                    "2002-10-04"),
    # ADV
    "ADV1-ja":  ("EX Ruby & Sapphire",   "ADV",                       "2003-01-31"),
    "ADV2-ja":  ("EX Sandstorm",         "ADV",                       "2003-04-18"),
    "ADV3-ja":  ("EX Dragon",            "ADV",                       "2003-06-25"),
    "ADV4-ja":  ("EX Team Magma vs Team Aqua", "ADV",                 "2003-10-24"),
    "ADV5-ja":  ("EX Hidden Legends",    "ADV",                       "2004-01-16"),
    # PCG
    "PCG1-ja":  ("EX FireRed & LeafGreen","PCG",                      "2004-04-09"),
    "PCG2-ja":  ("EX Deoxys",            "PCG",                       "2004-07-01"),
    "PCG3-ja":  ("EX Team Rocket Returns","PCG",                      "2004-10-15"),
    "PCG4-ja":  ("EX Gold Star",         "PCG",                       "2005-04-08"),
    "PCG5-ja":  ("EX Emerald",           "PCG",                       "2005-06-30"),
    "PCG6-ja":  ("EX Holon Phantoms",    "PCG",                       "2005-10-28"),
    "PCG7-ja":  ("EX Crystal Guardians", "PCG",                       "2006-01-27"),
    "PCG8-ja":  ("EX Dragon Frontiers",  "PCG",                       "2006-03-10"),
    "PCG9-ja":  ("EX Power Keepers",     "PCG",                       "2006-06-29"),
    "PCG10-ja": ("World Championships Pack", "PCG",                   "2007-07-05"),
    # LEGEND
    "L1a-ja":   ("HeartGold Collection", "LEGEND",                    "2009-10-09"),
    "L1b-ja":   ("SoulSilver Collection","LEGEND",                    "2009-10-09"),
    "L2-ja":    ("Reviving Legends",     "LEGEND",                    "2010-02-11"),
    "LL-ja":    ("Lost Link",            "LEGEND",                    "2010-04-16"),
    "L3-ja":    ("Clash at the Summit",  "LEGEND",                    "2010-07-08"),
    # XY
    "XY1a-ja":  ("Collection X",         "XY",                        "2013-12-13"),
    "XY1b-ja":  ("Collection Y",         "XY",                        "2013-12-13"),
    "XY2-ja":   ("Wild Blaze",           "XY",                        "2014-03-15"),
    "XY3-ja":   ("Rising Fist",          "XY",                        "2014-09-13"),
    "XY4-ja":   ("Phantom Gate",         "XY",                        "2014-09-13"),
    "XY5a-ja":  ("Gaia Volcano",         "XY",                        "2014-12-13"),
    "CP1-ja":   ("Double Crisis",        "XY",                        "2015-01-30"),
    "XY6-ja":   ("Emerald Break",        "XY",                        "2015-03-14"),
    "XY7-ja":   ("Bandit Ring",          "XY",                        "2015-06-20"),
    "CP2-ja":   ("Legendary Shine Collection", "XY",                  "2015-07-18"),
    "XY8a-ja":  ("Blue Impact",          "XY BREAK",                  "2015-09-26"),
    "XY8b-ja":  ("Red Flash",            "XY BREAK",                  "2015-09-26"),
    "XY9-ja":   ("Rage of the Broken Heavens", "XY BREAK",            "2015-12-11"),
    # SV
    "SV1S-ja":  ("Scarlet ex",           "Scarlet & Violet",          "2023-01-20"),
    "SV1V-ja":  ("Violet ex",            "Scarlet & Violet",          "2023-01-20"),
    "SV1a-ja":  ("Triplet Beat",         "Scarlet & Violet",          "2023-03-17"),
    "SV2D-ja":  ("Clay Burst",           "Scarlet & Violet",          "2023-04-14"),
    "SV2P-ja":  ("Snow Hazard",          "Scarlet & Violet",          "2023-04-14"),
    "SV2a-ja":  ("Pokémon Card 151",     "Scarlet & Violet",          "2023-06-16"),
    "SV3-ja":   ("Ruler of the Black Flame", "Scarlet & Violet",      "2023-07-28"),
    "SV3a-ja":  ("Raging Surf",          "Scarlet & Violet",          "2023-09-22"),
    "SV4K-ja":  ("Ancient Roar",         "Scarlet & Violet",          "2023-10-27"),
    "SV4M-ja":  ("Future Flash",         "Scarlet & Violet",          "2023-10-27"),
    "SV4a-ja":  ("Shiny Treasure ex",    "Scarlet & Violet",          "2023-12-01"),
    "SV5K-ja":  ("Wild Force",           "Scarlet & Violet",          "2024-01-26"),
    "SV5M-ja":  ("Cyber Judge",          "Scarlet & Violet",          "2024-01-26"),
    "SV5a-ja":  ("Crimson Haze",         "Scarlet & Violet",          "2024-03-22"),
    "SV6-ja":   ("Mask of Change",       "Scarlet & Violet",          "2024-04-26"),
    "SV6a-ja":  ("Night Wanderer",       "Scarlet & Violet",          "2024-06-07"),
    "SV7-ja":   ("Stellar Miracle",      "Scarlet & Violet",          "2024-07-19"),
    "SV7a-ja":  ("Paradise Dragona",     "Scarlet & Violet",          "2024-09-13"),
    "SV8-ja":   ("Electric Breaker",     "Scarlet & Violet",          "2024-10-18"),
    "SV8a-ja":  ("Terastal Festival ex", "Scarlet & Violet",          "2024-12-06"),
    "SV9-ja":   ("Battle Partners",      "Scarlet & Violet",          "2025-01-24"),
    "SV9a-ja":  ("Hot Wind Arena",       "Scarlet & Violet",          "2025-03-14"),
    "SV10-ja":  ("Glory of Team Rocket", "Scarlet & Violet",          "2025-04-18"),
    "SV11B-ja": ("Black Bolt",           "Scarlet & Violet",          "2025-06-06"),
    "SV11W-ja": ("White Flare",          "Scarlet & Violet",          "2025-06-06"),
    # MEGA
    "M1-ja":    ("Mega Brave",           "Mega Evolution",            "2025-08-01"),
    "M1S-ja":   ("Mega Symphonia",       "Mega Evolution",            "2025-08-01"),
    "M2-ja":    ("Inferno X",            "Mega Evolution",            "2025-09-26"),
    "M2pt5-ja": ("MEGA Dream ex",        "Mega Evolution",            "2025-11-28"),
    "M3-ja":    ("Nihil Zero",           "Mega Evolution",            "2026-01-23"),
    "M4-ja":    ("Ninja Spinner",        "Mega Evolution",            "2026-03-13"),
}


def main():
    print("Updating set metadata (name_en, series, release_date)...\n")

    updated = 0
    skipped = 0

    for set_id, (name_en, series, release_date) in SET_METADATA.items():
        sb.table("sets").update({
            "name_en": name_en,
            "series": series,
            "release_date": release_date,
        }).eq("id", set_id).execute()
        print(f"  {set_id}: {name_en} | {series} | {release_date}")
        updated += 1

    print(f"\nDone! Updated: {updated}")


if __name__ == "__main__":
    main()
