"""Backfill name_en for remaining JA sets missing English names (S-era, SV starters, CP/XY10)."""
import io
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

NAMES: dict[str, str] = {
    # Scarlet & Violet starters
    "SVLS-ja": "Scarlet ex",
    "SVLN-ja": "Violet ex",
    "SVK-ja":  "Scarlet & Violet Starter Set ex",

    # Sword & Shield (S-era)
    "S12a-ja": "VSTAR Universe",
    "S12-ja":  "Paradigm Trigger",
    "S11a-ja": "Incandescent Arcana",
    "S11-ja":  "Lost Abyss",
    "S10b-ja": "Pokémon GO",
    "S10a-ja": "Dark Phantasma",
    "S10D-ja": "Space Juggler",
    "S10P-ja": "Time Gazer",
    "S9a-ja":  "Battle Region",
    "S9-ja":   "Star Birth",
    "S8b-ja":  "VMAX Climax",
    "S8a-ja":  "25th Anniversary Collection",
    "S8-ja":   "Fusion Arts",
    "S7R-ja":  "Blue Sky Stream",
    "S7D-ja":  "Towering Perfection",
    "S6a-ja":  "Eevee Heroes",
    "S6K-ja":  "Jet-Black Poltergeist",
    "S6H-ja":  "Silver Lance",
    "S5a-ja":  "Matchless Fighters",
    "S5R-ja":  "Rapid Strike Master",
    "S5I-ja":  "Single Strike Master",
    "S4a-ja":  "Shiny Star V",
    "S4-ja":   "Amazing Volt Tackle",
    "S3a-ja":  "Legendary Heartbeat",
    "S3-ja":   "Infinity Zone",
    "S2a-ja":  "Explosive Walker",
    "S2-ja":   "Rebellion Crash",
    "S1a-ja":  "VMAX Rising",
    "S1H-ja":  "Shield",
    "S1W-ja":  "Sword",

    # XY / CP
    "XY10-ja": "Awakening Psychic King",
    "CP6-ja":  "20th Anniversary",
    "CP5-ja":  "Mythical & Legendary Dream Shine Collection",
    "CP4-ja":  "Premium Champion Pack",
    "CP3-ja":  "Pokekyun Collection",
}

applied = 0
for set_id, name_en in NAMES.items():
    sb.table("sets").update({"name_en": name_en}).eq("id", set_id).execute()
    applied += 1
    print(f"  {set_id:10}  {name_en}")
print(f"\nApplied {applied} name_en updates.")
