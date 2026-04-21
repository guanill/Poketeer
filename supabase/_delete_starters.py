"""Delete starter sets and their cards: SVK-ja, SVLN-ja, SVLS-ja, xy0."""
import io
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

IDS = ["SVK-ja", "SVLN-ja", "SVLS-ja", "xy0"]

for sid in IDS:
    cards = sb.table("cards").delete().eq("set_id", sid).execute()
    n_cards = len(cards.data) if cards.data else 0
    s = sb.table("sets").delete().eq("id", sid).execute()
    n_sets = len(s.data) if s.data else 0
    print(f"  {sid:10}  cards_deleted={n_cards:>3}  set_deleted={n_sets}")
