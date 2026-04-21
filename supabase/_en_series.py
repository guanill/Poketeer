"""Distribution of series values across EN sets."""
import io, os, sys
from collections import Counter
from dotenv import load_dotenv
from supabase import create_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

r = sb.table("sets").select("series,release_date").eq("language", "en").execute()
cnt = Counter(s.get("series") or "(null)" for s in r.data)
# Get earliest release date per series
first: dict[str, str] = {}
for s in r.data:
    k = s.get("series") or "(null)"
    rd = s.get("release_date") or ""
    if k not in first or rd < first[k]:
        first[k] = rd
for k in sorted(first, key=lambda x: first[x]):
    print(f"  {cnt[k]:>3}  {first[k]}  {k}")
