"""
update_mega_ja_names.py — Update MEGA-era JA sets and cards with proper Japanese names.

Sets are updated so `name` = Japanese name, displayed alongside English.
Cards are updated so `name` = Japanese (e.g. フシギダネ), `name_en` = English (e.g. Bulbasaur).

Sources:
  - Bulbapedia set wikitext for card listings (English names + card numbers)
  - Bulbapedia individual card pages for `jname` (Japanese Pokémon name)

Usage:
    python supabase/update_mega_ja_names.py           # all MEGA sets
    python supabase/update_mega_ja_names.py --set M1-ja
    python supabase/update_mega_ja_names.py --dry-run
"""

import io
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

API = "https://bulbapedia.bulbagarden.net/w/api.php"
UA = {"User-Agent": "poketeer-image-fetcher/1.0 (contact: dev)"}

# Bulbapedia page → {subset_name_in_wikitext: (db_set_id, ja_set_name)}
SET_PAGES = [
    {
        "page": "Mega_Brave/Mega_Symphonia_(TCG)",
        "subsets": {
            "Mega Brave":     ("M1-ja",  "メガブレイブ",    "Mega Brave"),
            "Mega Symphonia": ("M1S-ja", "メガシンフォニア", "Mega Symphonia"),
        },
    },
    {
        "page": "Inferno_X_(TCG)",
        "subsets": {
            "Inferno X": ("M2-ja", "インフェルノX", "Inferno X"),
        },
    },
    {
        "page": "MEGA_Dream_ex_(TCG)",
        "subsets": {
            "MEGA Dream ex": ("M2pt5-ja", "MEGAドリームex", "MEGA Dream ex"),
        },
    },
    {
        "page": "Nihil_Zero_(TCG)",
        "subsets": {
            "Nihil Zero": ("M3-ja", "ムニキスゼロ", "Nihil Zero"),
        },
    },
    {
        "page": "Ninja_Spinner_(TCG)",
        "subsets": {
            "Ninja Spinner": ("M4-ja", "ニンジャスピナー", "Ninja Spinner"),
        },
    },
]


def mw_get(params: dict) -> dict:
    for attempt in range(3):
        try:
            r = requests.get(API, params={**params, "format": "json"}, headers=UA, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    return {}


def parse_set_entries(page: str) -> list[dict]:
    """Return [{'subset': 'Mega Brave', 'pokemon': 'Bulbasaur', 'number': 1}, ...]"""
    data = mw_get({"action": "parse", "page": page, "prop": "wikitext"})
    wt = data.get("parse", {}).get("wikitext", {}).get("*", "")
    rx = re.compile(r"\{\{TCG ID\|([^|]+)\|([^|]+)\|(\d+)(?:\|[^}]*)?\}\}")
    results = []
    for m in rx.finditer(wt):
        results.append({
            "subset": m.group(1).strip(),
            "pokemon": m.group(2).strip(),
            "number": int(m.group(3)),
        })
    return results


def batch_get_jnames(entries: list[dict]) -> dict[str, str]:
    """Fetch jname for each card page in batches of 50.

    Returns {page_title: jname_or_empty_string}.
    Uses revisions API to get wikitext for multiple pages at once.
    Follows redirects automatically.
    """
    titles = [
        f"{e['pokemon']} ({e['subset']} {e['number']})".replace("_", " ")
        for e in entries
    ]
    out: dict[str, str] = {}

    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        data = mw_get({
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "redirects": "1",
        })
        pages = data.get("query", {}).get("pages", {})
        redirects = {r["from"]: r["to"] for r in data.get("query", {}).get("redirects", [])}

        for _, page_data in pages.items():
            title = page_data.get("title", "")
            revisions = page_data.get("revisions", [])
            if not revisions:
                continue
            content = revisions[0].get("slots", {}).get("main", {}).get("*", "") or ""
            m = re.search(r"\|jname=([^\|\n\}]+)", content)
            jname = m.group(1).strip() if m else ""
            # Store under both original title and redirected title
            out[title] = jname

        # Map original titles → jnames via redirect info
        for orig, redir in redirects.items():
            if redir in out:
                out[orig] = out[redir]

        if (i + 50) < len(titles):
            print(f"    {min(i + 50, len(titles))}/{len(titles)}")
        time.sleep(0.2)

    return out


def process_set_page(src: dict, target_set_id: str | None, dry_run: bool) -> None:
    print(f"\nFetching wikitext: {src['page']}")
    entries = parse_set_entries(src["page"])

    # Group by subset, filter to target
    by_subset: dict[str, list[dict]] = {}
    for e in entries:
        sub = src["subsets"].get(e["subset"])
        if not sub:
            continue
        db_set_id = sub[0]
        if target_set_id and db_set_id != target_set_id:
            continue
        by_subset.setdefault(db_set_id, []).append(e)

    if not by_subset:
        return

    # Fetch jnames for all cards in this page at once (more efficient)
    all_entries = [e for cards in by_subset.values() for e in cards]
    print(f"  Fetching Japanese names for {len(all_entries)} cards...")
    jname_map = batch_get_jnames(all_entries)
    print(f"    {min(50, len(all_entries))}/{len(all_entries)}" if len(all_entries) > 50 else "")

    for db_set_id, cards in by_subset.items():
        sub = src["subsets"].get(cards[0]["subset"])
        ja_name, en_name = sub[1], sub[2]

        print(f"\n  {db_set_id} — {ja_name} ({en_name}): {len(cards)} cards")

        # Update set name
        if not dry_run:
            sb.table("sets").update({"name": ja_name}).eq("id", db_set_id).execute()
        else:
            print(f"    Would set sets.name = '{ja_name}' (en: {en_name})")

        # Build card updates
        base_id = db_set_id.removesuffix("-ja")
        updates = []
        missing_jname = 0
        for e in cards:
            title = f"{e['pokemon']} ({e['subset']} {e['number']})"
            jname = jname_map.get(title, "")
            if not jname:
                missing_jname += 1
                jname = e["pokemon"]  # fall back to English
            card_id = f"{base_id}-{e['number']:03d}-ja"
            updates.append({
                "id": card_id,
                "name": jname,
                "name_en": e["pokemon"],
            })

        print(f"    {len(updates)} updates ({missing_jname} fell back to English)")

        if dry_run:
            for u in updates[:5]:
                print(f"      {u['id']}: {u['name']} / {u['name_en']}")
            if len(updates) > 5:
                print(f"      ... and {len(updates) - 5} more")
            continue

        # Apply updates in batches
        for i in range(0, len(updates), 200):
            chunk = updates[i : i + 200]
            for u in chunk:
                sb.table("cards").update({
                    "name": u["name"],
                    "name_en": u["name_en"],
                }).eq("id", u["id"]).execute()
            print(f"    {min(i + 200, len(updates))}/{len(updates)} updated", end="\r")
        print()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", help="Only process this set (e.g. M1-ja)")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = ap.parse_args()

    print(f"Updating MEGA JA set + card names from Bulbapedia...")
    for src in SET_PAGES:
        # Quick check: does any subset match the target?
        if args.set:
            relevant = any(v[0] == args.set for v in src["subsets"].values())
            if not relevant:
                continue
        process_set_page(src, target_set_id=args.set, dry_run=args.dry_run)

    print("\nAll done!")


if __name__ == "__main__":
    main()
