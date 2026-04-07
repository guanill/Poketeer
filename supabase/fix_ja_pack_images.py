"""
fix_ja_pack_images.py — Copy pack images from Thai sets to matching Japanese sets.
The sets share the same expansion codes and pack designs.
"""

import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def main():
    print("Copying pack images from Thai sets to Japanese sets...\n")

    # Get all Thai sets that have logo_url
    th_res = sb.table("sets").select("id, logo_url").like("id", "%-th").neq("logo_url", "").execute()
    th_sets = {r["id"].removesuffix("-th"): r["logo_url"] for r in (th_res.data or []) if r.get("logo_url")}
    print(f"  Thai sets with images: {len(th_sets)}")

    # Get all Japanese sets
    ja_res = sb.table("sets").select("id, logo_url").like("id", "%-ja").execute()
    ja_sets = {r["id"].removesuffix("-ja"): r for r in (ja_res.data or [])}
    print(f"  Japanese sets total: {len(ja_sets)}")

    updates = 0
    for code, logo in th_sets.items():
        if code in ja_sets:
            ja_set = ja_sets[code]
            if not ja_set.get("logo_url"):
                ja_id = f"{code}-ja"
                sb.table("sets").update({"logo_url": logo}).eq("id", ja_id).execute()
                print(f"  {ja_id} <- {logo[:60]}...")
                updates += 1

    print(f"\nUpdated {updates} Japanese sets with pack images. Done!")


if __name__ == "__main__":
    main()
