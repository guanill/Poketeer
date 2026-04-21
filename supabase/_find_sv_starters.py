"""Search for any Violet/Scarlet ex starter rows in the sets table."""
import io, os, sys
from dotenv import load_dotenv
from supabase import create_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

for q in ["Violet", "Scarlet", "スターター", "ステラ", "ニンフィア", "ソウブレイズ", "SVL", "SVK"]:
    r = sb.table("sets").select("id,name,name_en,language,series").or_(
        f"name.ilike.%{q}%,name_en.ilike.%{q}%,id.ilike.%{q}%"
    ).execute()
    if r.data:
        print(f"\n=== query '{q}' -> {len(r.data)} hits ===")
        for row in r.data:
            print(f"  {row['id']:14}  lang={row.get('language'):2}  {row['name']}  ({row.get('name_en') or '-'})")
