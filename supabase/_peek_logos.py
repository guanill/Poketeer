"""Peek current logo_url values to understand storage pattern."""
import io, os, sys
from dotenv import load_dotenv
from supabase import create_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

ids = ["PMCG1-ja", "PMCG2-ja", "PMCG3-ja", "PMCG4-ja", "SM0-ja", "SM12-ja"]
res = sb.table("sets").select("id,logo_url,symbol_url").in_("id", ids).execute()
for r in res.data:
    print(f"  {r['id']:10}  logo={r.get('logo_url')}")
    print(f"             symbol={r.get('symbol_url')}")
