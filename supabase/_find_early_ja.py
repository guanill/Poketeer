"""Find the JA sets corresponding to Base/Jungle/Fossil/Team Rocket + verify SV starters."""
import io
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Base/Jungle/Fossil/Rocket era — usually series='Pocket Monsters Card Game'
r1 = sb.table("sets").select("id,name,name_en,series,release_date,logo_url").eq("series", "Pocket Monsters Card Game").order("release_date").execute()
print("=== Pocket Monsters Card Game (Base-era JA) ===")
for r in r1.data:
    has_logo = "Y" if r.get("logo_url") else "."
    print(f"  [{has_logo}]  {r['id']:12}  {r.get('release_date','')}  {r['name']}  ({r.get('name_en') or '-'})")

# SM0-ja
r2 = sb.table("sets").select("id,name,name_en,logo_url").eq("id", "SM0-ja").execute()
print("\n=== SM0-ja ===")
for r in r2.data:
    has_logo = "Y" if r.get("logo_url") else "."
    print(f"  [{has_logo}]  {r['id']:12}  {r['name']}  ({r.get('name_en') or '-'})")

# Violet ex / Scarlet ex
r3 = sb.table("sets").select("id,name,name_en").in_("id", ["SVLN-ja", "SVLS-ja", "SVK-ja"]).execute()
print("\n=== SV starters (deleted earlier?) ===")
print(f"  rows returned: {len(r3.data)}")
for r in r3.data:
    print(f"  {r['id']}  {r['name']}")
