"""List likely starter/bundle sets to review before deleting."""
import io
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

res = sb.table("sets").select("id,name,name_en,series,total").order("id").execute()

keywords = ["starter", "Starter", "スターター", "Deck", "deck", "デッキ",
            "Half Deck", "Preconstructed", "Theme", "Trainer's Toolkit",
            "Battle Academy", "Battle Deck", "Build", "Bundle"]

hits = []
for r in res.data:
    blob = f"{r.get('name','')} {r.get('name_en','')}"
    if any(k in blob for k in keywords):
        hits.append(r)

print(f"Starter/deck-ish sets: {len(hits)}\n")
for r in hits:
    en = r.get("name_en") or ""
    print(f"  {r['id']:14}  total={r.get('total',0):>4}  {r['name']:40}  {en}")
