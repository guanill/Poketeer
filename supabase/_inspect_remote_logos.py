"""Count JA sets whose logo_url still points to an external CDN (not our Supabase storage)."""
import io, os, sys
from collections import Counter
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
load_dotenv(".env.seed")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

SUPABASE_HOST = urlparse(os.getenv("SUPABASE_URL", "")).netloc

r = sb.table("sets").select("id,name,logo_url").eq("language", "ja").execute()
remote = [s for s in r.data if s.get("logo_url") and SUPABASE_HOST not in s["logo_url"]]
hosts = Counter(urlparse(s["logo_url"]).netloc for s in remote)
print(f"JA sets total: {len(r.data)}")
print(f"Remote-hosted (not in our bucket): {len(remote)}")
for h, n in hosts.most_common():
    print(f"  {n:>4}  {h}")
