"""
cache_intl_cards.py — Bulk pre-cache all JP/TH card data locally.

Reads sets_ja.json and sets_th.json, fetches each set's cards from
tcgdex.net, and saves them to _intl_cards_cache/ in exactly the same
format the backend uses, so the server never needs a live tcgdex call.

Usage:
    python cache_intl_cards.py            # all JP + TH sets
    python cache_intl_cards.py --lang ja  # JP only
    python cache_intl_cards.py --lang th  # TH only
    python cache_intl_cards.py --refresh  # re-fetch even if already cached
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "_intl_cards_cache"
SETS_JA_PATH = BASE_DIR / "sets_ja.json"
SETS_TH_PATH = BASE_DIR / "sets_th.json"
CACHE_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "poketeer/1.0"


def cache_path(lang: str, set_id: str) -> Path:
    return CACHE_DIR / f"{lang}_{set_id}.json"


def load_sets(lang: str) -> list[dict]:
    path = SETS_JA_PATH if lang == "ja" else SETS_TH_PATH
    if not path.exists():
        print(f"[warn] {path} not found, skipping {lang}")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tcgdex_card_to_api(card: dict, set_id: str, lang: str, set_info: dict,
                       serie_id: str = "") -> dict:
    """Mirror of main.py's _tcgdex_card_to_api."""
    local_id = card.get("localId", "")
    image_base = card.get("image", "")
    if not image_base and serie_id and local_id:
        image_base = f"https://assets.tcgdex.net/{lang}/{serie_id}/{set_id}/{local_id}"
    return {
        "id": card["id"],
        "name": card.get("name") or "",
        "supertype": "Pokémon",
        "subtypes": [],
        "hp": "",
        "types": [],
        "number": local_id,
        "artist": "",
        "rarity": card.get("rarity") or "",
        "set": {
            "id": set_id,
            "name": set_info.get("name", set_id),
            "series": set_info.get("series", ""),
            "images": set_info.get("images", {"symbol": "", "logo": ""}),
        },
        "images": {
            "small": f"{image_base}/low.webp" if image_base else "",
            "large": f"{image_base}/high.webp" if image_base else "",
        },
        "language": lang,
    }


def fetch_set(lang: str, set_info: dict, refresh: bool) -> tuple[str, int, str]:
    """
    Fetch and cache one set.
    Returns (set_id, card_count, status) where status is 'cached'|'fetched'|'empty'|'error'.
    """
    set_id = set_info["id"]
    p = cache_path(lang, set_id)

    # Skip if already cached and not refreshing
    if not refresh and p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            count = len(data.get("cards", []))
            # If it's empty but older than 24h, re-try in case tcgdex got updated
            age = time.time() - data.get("updated", 0)
            if count > 0 or age < 86400:
                return set_id, count, "cached"
        except Exception:
            pass  # file corrupted — re-fetch

    try:
        resp = SESSION.get(
            f"https://api.tcgdex.net/v2/{lang}/sets/{quote(set_id, safe='')}",
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        raw_cards = body.get("cards", [])
        serie_id = (body.get("serie") or {}).get("id", "")
        cards = [tcgdex_card_to_api(c, set_id, lang, set_info, serie_id) for c in raw_cards]

        payload = {"cards": cards, "updated": time.time()}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        status = "fetched" if cards else "empty"
        return set_id, len(cards), status

    except Exception as exc:
        return set_id, 0, f"error: {exc}"


def run(lang: str, refresh: bool, workers: int = 10) -> None:
    sets = load_sets(lang)
    if not sets:
        return

    total = len(sets)
    print(f"\n[{lang.upper()}] Caching {total} sets with {workers} workers...")

    results = {"fetched": 0, "cached": 0, "empty": 0, "error": 0}
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_set, lang, s, refresh): s["id"] for s in sets}
        for fut in as_completed(futures):
            set_id, count, status = fut.result()
            done += 1
            if status.startswith("error"):
                results["error"] += 1
                key = "error"
            elif status == "empty":
                results["empty"] += 1
                key = "empty"
            elif status == "cached":
                results["cached"] += 1
                key = "cached"
            else:
                results["fetched"] += 1
                key = "fetched"

            symbol = {"fetched": "+", "cached": ".", "empty": "o", "error": "!"}.get(key, "?")
            print(f"  [{done:3}/{total}] {symbol} {lang}/{set_id:12} {count:4} cards  ({status})")

    print(f"\n[{lang.upper()}] Summary: {results['fetched']} fetched, {results['cached']} already cached, "
          f"{results['empty']} empty (no tcgdex data), {results['error']} errors")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-cache JP/TH card data locally")
    parser.add_argument("--lang", choices=["ja", "th", "both"], default="both")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch even if cached")
    parser.add_argument("--workers", type=int, default=10, help="Parallel fetch workers")
    args = parser.parse_args()

    langs = ["ja", "th"] if args.lang == "both" else [args.lang]
    for lang in langs:
        run(lang, refresh=args.refresh, workers=args.workers)

    print("\nDone! Restart the backend (or call POST /index/reload) to apply changes.")


if __name__ == "__main__":
    main()
