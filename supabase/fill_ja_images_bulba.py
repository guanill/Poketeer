"""
fill_ja_images_bulba.py — Fetch JA card images from Bulbapedia for sets
that TCGdex hasn't uploaded yet (SV11B, SV11W, M1S, M3).

Strategy:
  1. Fetch Bulbapedia set page wikitext, parse {{Setlist/entry|...|{{TCG ID|Set|Pokemon|N}}|...}}
  2. Batch fetch card pages (50 per request) → extract image filename like "PokemonSeriesN.jpg"
  3. Batch resolve filenames → CDN URLs via imageinfo API
  4. Upsert image_small / image_large into Supabase (cards are language-suffixed '-ja')
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

# Bulbapedia set page → (series name as used in image filenames, our DB set_id prefix)
# The "combined" set pages contain multiple sub-sets (e.g. Black Bolt AND White Flare).
# We parse them all at once and route by the TCG ID set name.
SET_PAGES = [
    {
        "page": "Black_Bolt/White_Flare_(TCG)",
        "subsets": {
            # Bulbapedia set name in {{TCG ID}} : (our DB set_id, image filename series token)
            "Black Bolt": ("SV11B-ja", "BlackBolt"),
            "White Flare": ("SV11W-ja", "WhiteFlare"),
        },
    },
    {
        "page": "Mega_Brave/Mega_Symphonia_(TCG)",
        "subsets": {
            "Mega Symphonia": ("M1S-ja", "MegaSymphonia"),
            "Mega Brave": ("M1-ja", "MegaBrave"),
        },
    },
    {
        "page": "Munikisu_Zero_(TCG)",
        "subsets": {
            "Munikisu Zero": ("M3-ja", "MunikisuZero"),
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
    """Return [{'subset':'Black Bolt','pokemon':'Snivy','number':1}, ...]"""
    data = mw_get({"action": "parse", "page": page, "prop": "wikitext"})
    wt = data.get("parse", {}).get("wikitext", {}).get("*", "")
    # {{Setlist/entry|NNN/TTT|rm|{{TCG ID|SetName|Pokemon|N[|disambig]}}...|...}}
    rx = re.compile(r"\{\{TCG ID\|([^|]+)\|([^|]+)\|(\d+)(?:\|[^}]*)?\}\}")
    results = []
    for m in rx.finditer(wt):
        results.append({
            "subset": m.group(1).strip(),
            "pokemon": m.group(2).strip(),
            "number": int(m.group(3)),
        })
    return results


def page_title(pokemon: str, subset: str, number: int) -> str:
    return f"{pokemon} ({subset} {number})".replace(" ", "_")


def batch_get_images(titles: list[str]) -> dict[str, tuple[list[str], str]]:
    """For each title, return (image_filenames, resolved_page_title).

    Uses single-title requests because MediaWiki's imlimit is per-query total,
    which gets distributed across batched titles and silently truncates.
    Follows redirects and returns the resolved title so callers can infer the
    correct series token from it (e.g. 'Mega Evolution 6' not 'Mega Symphonia 1').
    """
    out: dict[str, tuple[list[str], str]] = {}
    for i, t in enumerate(titles):
        data = mw_get({
            "action": "query",
            "titles": t.replace("_", " "),
            "prop": "images",
            "imlimit": "50",
            "redirects": "1",
        })
        pages = data.get("query", {}).get("pages", {})
        imgs: list[str] = []
        resolved_title: str = t.replace("_", " ")
        for _, p in pages.items():
            imgs = [img["title"].removeprefix("File:") for img in p.get("images", [])]
            resolved_title = p.get("title", resolved_title)
            break
        out[t] = (imgs, resolved_title)
        if (i + 1) % 25 == 0:
            print(f"    {i + 1}/{len(titles)}")
        time.sleep(0.1)
    return out


def batch_resolve_urls(filenames: list[str]) -> dict[str, str]:
    """Map each filename → CDN URL."""
    out: dict[str, str] = {}
    for i in range(0, len(filenames), 50):
        chunk = filenames[i : i + 50]
        titles = "|".join(f"File:{f}" for f in chunk)
        data = mw_get({
            "action": "query",
            "titles": titles,
            "prop": "imageinfo",
            "iiprop": "url",
        })
        pages = data.get("query", {}).get("pages", {})
        for _, p in pages.items():
            title = p.get("title", "").removeprefix("File:")
            info = p.get("imageinfo", [])
            if info:
                out[title] = info[0]["url"]
        time.sleep(0.1)
    return out


def infer_series_token_and_number(resolved_title: str) -> tuple[str, int | None]:
    """Extract series token and global number from a resolved Bulbapedia page title.

    e.g. "Tangela (Mega Evolution 6)"  → ("MegaEvolution", 6)
         "Snivy (Black Bolt 1)"        → ("BlackBolt", 1)
    """
    m = re.search(r"\((.+?)\s+(\d+)\)$", resolved_title)
    if not m:
        return ("", None)
    series = re.sub(r"[^A-Za-z0-9]", "", m.group(1))
    return (series, int(m.group(2)))


def pick_card_image(images: list[str], pokemon: str, resolved_title: str) -> str | None:
    """Pick the main card art from a page's image list.

    Uses the resolved page title to infer the correct series token and global
    card number — needed because Mega set cards redirect to different titles.
    """
    pokemon_key = re.sub(r"[^A-Za-z0-9]", "", pokemon)
    series_token, global_n = infer_series_token_and_number(resolved_title)

    candidates = [
        img for img in images
        if img.lower().endswith(".jpg")
        and pokemon_key.lower() in re.sub(r"[^A-Za-z0-9]", "", img).lower()
        and series_token.lower() in img.lower()
    ]
    if not candidates:
        # Broader fallback: just match pokemon name
        candidates = [
            img for img in images
            if img.lower().endswith(".jpg")
            and pokemon_key.lower() in re.sub(r"[^A-Za-z0-9]", "", img).lower()
        ]
    if not candidates:
        return None
    # Prefer filename whose trailing number matches the global card number
    if global_n is not None:
        expected = re.compile(rf"{global_n}\.jpg$", re.IGNORECASE)
        for c in candidates:
            if expected.search(c):
                return c
    # Fallback: shortest (usually the base printing, not alternate arts)
    candidates.sort(key=len)
    return candidates[0]


def process_target_set(target_set_id: str | None = None, limit: int | None = None):
    all_entries: list[dict] = []
    for src in SET_PAGES:
        print(f"\nFetching wikitext: {src['page']}")
        entries = parse_set_entries(src["page"])
        for e in entries:
            sub = src["subsets"].get(e["subset"])
            if not sub:
                continue
            db_set_id, series_token = sub
            if target_set_id and db_set_id != target_set_id:
                continue
            all_entries.append({
                **e,
                "db_set_id": db_set_id,
                "series_token": series_token,
            })

    print(f"\nTotal entries to resolve: {len(all_entries)}")
    if limit:
        all_entries = all_entries[:limit]
        print(f"  limited to first {limit} for testing")

    # Step 2: batch fetch image lists
    titles = [page_title(e["pokemon"], e["subset"], e["number"]) for e in all_entries]
    print(f"\nFetching card pages (batched)...")
    page_images = batch_get_images(titles)

    # Step 3: pick the main card image for each
    filenames_needed: set[str] = set()
    for e, title in zip(all_entries, titles):
        images, resolved_title = page_images.get(title, ([], title.replace("_", " ")))
        fname = pick_card_image(images, e["pokemon"], resolved_title)
        e["filename"] = fname
        if fname:
            filenames_needed.add(fname)

    missing = sum(1 for e in all_entries if not e["filename"])
    print(f"  Found image filename for {len(all_entries) - missing}/{len(all_entries)} cards")

    # Step 4: resolve filenames → URLs
    print(f"\nResolving {len(filenames_needed)} image URLs...")
    url_map = batch_resolve_urls(list(filenames_needed))

    # Step 5: build DB updates
    updates = []
    no_url = 0
    for e in all_entries:
        if not e["filename"]:
            continue
        url = url_map.get(e["filename"])
        if not url:
            no_url += 1
            continue
        card_id = f"{e['db_set_id'].removesuffix('-ja')}-{e['number']:03d}-ja"
        updates.append({
            "id": card_id,
            "image_small": url,
            "image_large": url,
            "name_en": e["pokemon"],
        })

    print(f"\nPrepared {len(updates)} card updates (missing image: {missing}, no url resolved: {no_url})")

    # Step 6: upsert in batches (update-only via id)
    print("\nUpserting to Supabase...")
    for i in range(0, len(updates), 200):
        chunk = updates[i : i + 200]
        # upsert requires full row data; use update per card id via RPC-less approach
        for u in chunk:
            sb.table("cards").update({
                "image_small": u["image_small"],
                "image_large": u["image_large"],
                "name_en": u["name_en"],
            }).eq("id", u["id"]).execute()
        print(f"  {min(i + 200, len(updates))}/{len(updates)}", end="\r")
    print()
    print("Done!")


if __name__ == "__main__":
    # Test mode: --test to run on just SV11B first 10
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", help="Only process this set (e.g. SV11B-ja)")
    ap.add_argument("--limit", type=int, help="Limit number of cards (for testing)")
    args = ap.parse_args()
    process_target_set(target_set_id=args.set, limit=args.limit)
