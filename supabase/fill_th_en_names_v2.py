"""
fill_th_en_names_v2.py — Fill English names for Thai cards by matching
card numbers against Japanese cards that already have name_en populated.
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

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))


def main():
    print("Filling English names for Thai cards (v2 — from JA cards)...\n")

    # Get all Thai cards without English names
    print("Fetching Thai cards without name_en...")
    th_cards = []
    page = 0
    while True:
        res = (sb.table("cards")
               .select("id, number, set_id")
               .like("set_id", "%-th")
               .eq("name_en", "")
               .range(page * 1000, (page + 1) * 1000 - 1)
               .execute())
        if not res.data:
            break
        th_cards.extend(res.data)
        page += 1
    print(f"  Found {len(th_cards)} cards\n")

    if not th_cards:
        print("Nothing to do!")
        return

    # Group by set code
    by_set: dict[str, list[dict]] = {}
    for c in th_cards:
        code = c["set_id"].removesuffix("-th")
        by_set.setdefault(code, []).append(c)

    # For each set, look up name_en from the matching JA set
    total_matched = 0
    total_cards = 0

    for code, cards in sorted(by_set.items()):
        ja_set_id = f"{code}-ja"
        total_cards += len(cards)

        # Get all JA cards with name_en for this set
        name_map: dict[str, str] = {}
        ref_page = 0
        while True:
            res = (sb.table("cards")
                   .select("number, name_en")
                   .eq("set_id", ja_set_id)
                   .neq("name_en", "")
                   .range(ref_page * 1000, (ref_page + 1) * 1000 - 1)
                   .execute())
            if not res.data:
                break
            for r in res.data:
                if r.get("name_en"):
                    num = r["number"]
                    name_map[num] = r["name_en"]
                    # Also store stripped/padded variants for cross-matching
                    name_map[num.lstrip("0") or "0"] = r["name_en"]
                    name_map[num.zfill(3)] = r["name_en"]
            ref_page += 1

        matched = 0
        for c in cards:
            en = name_map.get(c["number"])
            if en:
                sb.table("cards").update({"name_en": en}).eq("id", c["id"]).execute()
                matched += 1

        total_matched += matched
        if matched > 0 or len(name_map) > 0:
            print(f"  [{code}] {matched}/{len(cards)} matched (JA has {len(name_map)} with name_en)")

    print(f"\nTotal: {total_matched}/{total_cards} Thai cards got English names")
    print("Done!")


if __name__ == "__main__":
    main()
