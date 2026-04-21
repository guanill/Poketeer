"""Search for the World Champions Pack JA set."""
import io, os, sys
from dotenv import load_dotenv
from supabase import create_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

for q in ["World", "Champion", "ワールド", "チャンピオン", "WCS", "PCG"]:
    r = sb.table("sets").select("id,name,name_en,language,release_date").or_(
        f"name.ilike.%{q}%,name_en.ilike.%{q}%,id.ilike.%{q}%"
    ).execute()
    if r.data:
        print(f"\n=== query '{q}' -> {len(r.data)} hits ===")
        for row in sorted(r.data, key=lambda x: x.get("release_date") or ""):
            print(f"  {row['id']:14}  lang={row.get('language'):2}  {row.get('release_date','')}  {row['name']}  ({row.get('name_en') or '-'})")
