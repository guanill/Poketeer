"""Verify SM sets have language='ja' and name_en populated as the frontend expects."""
import io
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

res = sb.table("sets").select("id,name,name_en,series,language").like("id", "SM%-ja").execute()
print(f"SM-ja row count: {len(res.data)}")
for r in sorted(res.data, key=lambda x: x["id"])[:5]:
    print(f"  {r}")

# Simulate the frontend query
res2 = sb.table("sets").select("*").eq("language", "ja").order("release_date", desc=True).execute()
print(f"\nFrontend query (.eq('language','ja')): {len(res2.data)} rows")
sm_in = [r for r in res2.data if r["id"].lower().startswith("sm") or r["id"].lower().startswith("sn")]
print(f"  of which SM/sn: {len(sm_in)}")
missing_en = [r for r in sm_in if not r.get("name_en")]
print(f"  SM missing name_en in that result: {len(missing_en)}")
