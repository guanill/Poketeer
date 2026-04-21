"""Backfill name_en for Sun & Moon era JA sets that are missing English names."""
import io
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

SM_NAMES: dict[str, str] = {
    "SM12a-ja": "Tag All Stars",
    "SM12-ja":  "Alter Genesis",
    "SM11b-ja": "Dream League",
    "SM11a-ja": "Remix Bout",
    "sn11-ja":  "Miracle Twin",
    "SM10b-ja": "Sky Legend",
    "SMP2-ja":  "Detective Pikachu",
    "sn10a-ja": "GG End",
    "SM10-ja":  "Double Blaze",
    "SM9b-ja":  "Full Metal Wall",
    "SM9a-ja":  "Night Unison",
    "SM9-ja":   "Tag Bolt",
    "SM8b-ja":  "GX Ultra Shiny",
    "SM8a-ja":  "Dark Order",
    "SM8-ja":   "Super Burst Impact",
    "SM7a-ja":  "Thunderclap Spark",
    "SM7b-ja":  "Fairy Rise",
    "SM7-ja":   "Charisma of the Wrecked Sky",
    "SM6b-ja":  "Champion Road",
    "SM6a-ja":  "Dragon Storm",
    "SM6-ja":   "Forbidden Light",
    "SM5+-ja":  "Ultra Force",
    "SM5S-ja":  "Ultra Sun",
    "SM5M-ja":  "Ultra Moon",
    "SM4+-ja":  "GX Battle Boost",
    "SM4A-ja":  "Ultradimensional Beasts",
    "SM4S-ja":  "Awakened Heroes",
    "SM3+-ja":  "Shining Legends",
    "SM3N-ja":  "Darkness that Consumes Light",
    "SM3H-ja":  "To Have Seen the Battle Rainbow",
    "sm2+-ja":  "Facing a New Trial",
    "SM2L-ja":  "Alolan Moonlight",
    "SM2K-ja":  "Islands Await You",
    "SM1+-ja":  "Sun & Moon",
    "SM1S-ja":  "Collection Sun",
    "SM1M-ja":  "Collection Moon",
    "SM0-ja":   "Pikachu and New Friends",
}

applied = 0
for set_id, name_en in SM_NAMES.items():
    sb.table("sets").update({"name_en": name_en}).eq("id", set_id).execute()
    applied += 1
    print(f"  {set_id:10}  {name_en}")
print(f"\nApplied {applied} name_en updates.")
