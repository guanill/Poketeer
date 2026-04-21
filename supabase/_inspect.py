import io, os, sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

res = sb.table("sets").select("id,name,name_en,series").like("id", "%-ja").order("release_date", desc=True).execute()
missing = [r for r in res.data if not r.get("name_en")]
print(f"JA sets missing name_en: {len(missing)}")
for r in missing:
    print(f"  {r['id']:12}  series={r['series']!r:30}  name={r['name']}")
