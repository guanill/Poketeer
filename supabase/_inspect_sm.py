"""Check SM-era sets and what series values exist for JA sets."""
import io
import os
import sys
from collections import Counter
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

res = sb.table("sets").select("id,name,name_en,series").like("id", "%-ja").execute()

print("=== SM-era JA sets (id starts with SM or sm) ===")
for r in sorted(res.data, key=lambda x: x["id"]):
    if r["id"].lower().startswith("sm") or r["id"].lower().startswith("sn"):
        print(f"  {r['id']:12}  series={r['series']!r:40}  name_en={r.get('name_en')!r}")

print("\n=== Distribution of series across ALL JA sets ===")
cnt = Counter(r.get("series") or "(null)" for r in res.data)
for s, n in sorted(cnt.items(), key=lambda x: -x[1]):
    print(f"  {n:>4}  {s!r}")
