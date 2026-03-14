"""
fetch_intl_sets.py
==================
One-time script that downloads Japanese and Thai Pokémon TCG set data from
the tcgdex.net API (free, no key required) and saves them as:
  - sets_ja.json   (Japanese sets)
  - sets_th.json   (Thai sets)

in the same format as sets.json (PokemonSet-compatible).

Run once:
  python fetch_intl_sets.py

Re-run any time to refresh the data.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

TCGDEX_BASE = "https://api.tcgdex.net/v2"
HEADERS = {"User-Agent": "poketeer/1.0"}
OUT_DIR = Path(__file__).resolve().parent.parent

LANGS = {
    "ja": "Japanese",
    "th": "Thai",
}


def get_en_logo_map() -> dict[str, tuple[str, str]]:
    """
    Fetch the tcgdex English sets list which includes logo & symbol URLs.
    Returns a dict of  en_set_id → (logo_url_webp, symbol_url_webp).

    NOTE: tcgdex's CDN only serves logo images for English sets.
    JP/TH sets do NOT have logo assets on assets.tcgdex.net — every JP/TH
    logo URL (e.g. /ja/SV/SV9/logo.webp) returns 404.  This map is kept
    here as future scaffolding in case the situation changes, but is no
    longer applied to JP/TH records.
    """
    try:
        r = requests.get(f"{TCGDEX_BASE}/en/sets", headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [!] Could not fetch EN sets for logo map: {e}")
        return {}

    result: dict[str, tuple[str, str]] = {}
    for s in r.json():
        logo = s.get("logo") or ""
        symbol = s.get("symbol") or ""
        if logo or symbol:
            result[s["id"]] = (
                f"{logo}.webp" if logo else "",
                f"{symbol}.webp" if symbol else "",
            )
    print(f"  EN logo map built: {len(result)} sets with images")
    return result


# Hardcoded overrides for JP/TH sets where EN set IDs don't follow the numeric
# pattern.  e.g. JP split-release sets whose cards were combined into one EN
# set, or sub-expansions with a completely different EN numbering.
_SET_ID_EN_OVERRIDES: dict[str, str] = {
    # JP "151" / TH "151" — numbered SV2a in JP but EN calls it sv03.5
    "SV2a": "sv03.5",
    # JP/TH "Shiny Treasure ex" — JP uses SV4a, EN calls it Paldean Fates (sv04.5)
    "SV4a": "sv04.5",
    # JP/TH dual-release Scarlet ex / Violet ex → combined EN "Scarlet & Violet"
    "SV1S": "sv01",
    "SV1V": "sv01",
    # JP split-release Wild Force / Cyber Judge → combined EN Paradox Rift (sv04)
    "SV4K": "sv04",
    "SV4M": "sv04",
    # JP split-release Snow Hazard / Clay Burst → combined EN Paldea Evolved (sv02)
    "SV2P": "sv02",
    "SV2D": "sv02",
    # JP Temporal Forces split → EN sv05
    "SV5K": "sv05",
    "SV5M": "sv05",
    # "White Flare" / "Black Bolt" split EN names match JP SV11 suffixes
    "SV11W": "sv10.5w",
    "SV11B": "sv10.5b",
}


def normalize_to_en_id(set_id: str) -> str | None:
    """
    Derive the tcgdex EN set ID from a JP/TH set ID so we can look up its logo.
    Examples:
      SV9   → sv09     (single digit zero-padded)
      SV10  → sv10
      SV3.5 → sv03.5
      SV6a  → sv06a   (may not exist in EN)
      SV11W → sv10.5w (via override table)
      CS1b  → None    (JP/TH-exclusive, no EN pattern)
    """
    # Check the override table first
    upper_id = set_id.upper()
    if upper_id in _SET_ID_EN_OVERRIDES:
        return _SET_ID_EN_OVERRIDES[upper_id]

    m = re.match(r"^([A-Za-z]+)([0-9]+(?:\.[0-9]+)?)([A-Za-z]*)$", set_id)
    if not m:
        return None
    prefix = m.group(1).lower()
    num_str = m.group(2)          # e.g. "9", "10", "3.5"
    suffix = m.group(3).lower()   # e.g. "a", "w", ""
    # Only map series prefixes that have EN counterparts in tcgdex
    if prefix not in ("sv", "bw", "xy", "sm", "swsh", "dp", "ex"):
        return None
    # Zero-pad the numeric part when it's a plain integer < 10
    try:
        int_part = int(num_str)
        padded = f"{int_part:02d}"
    except ValueError:
        padded = num_str  # e.g. "3.5" stays as-is
    return f"{prefix}{padded}{suffix}"


def fetch_set_detail(lang: str, set_id: str, session: requests.Session) -> dict | None:
    """Fetch full set detail (includes releaseDate and serie)."""
    try:
        r = session.get(f"{TCGDEX_BASE}/{lang}/sets/{set_id}", timeout=12)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [!] Error fetching {lang}/{set_id}: {e}")
    return None


def build_set_record(
    summary: dict,
    detail: dict | None,
    lang: str,
    en_logo_map: dict[str, tuple[str, str]] | None = None,
) -> dict:
    """Convert tcgdex set summary + detail into our PokemonSet format."""
    set_id = summary["id"]
    serie_name = (detail or {}).get("serie", {}).get("name", "") if detail else ""
    release_date = (detail or {}).get("releaseDate", "") if detail else ""
    official_count = summary.get("cardCount", {}).get("official", 0)
    total_count = summary.get("cardCount", {}).get("total", 0)

    # tcgdex's CDN does NOT host logo/symbol images for JP/TH sets.
    # All JP/TH logo asset URLs return 404 (e.g. /ja/SV/SV9/logo.webp).
    # Leave empty so SetCard renders the localised name-banner fallback
    # instead of a broken <img> or the wrong-language EN artwork.
    logo_url = ""
    symbol_url = ""

    return {
        "id": set_id,
        "name": summary["name"],
        "series": serie_name,
        "printedTotal": official_count,
        "total": total_count,
        "releaseDate": release_date,
        "language": lang,
        "images": {
            "symbol": symbol_url,
            "logo": logo_url,
        },
    }


def fetch_lang_sets(lang: str, en_logo_map: dict[str, tuple[str, str]] | None = None) -> list[dict]:
    label = LANGS.get(lang, lang)
    print(f"\n{'='*50}")
    print(f"Fetching {label} ({lang}) sets from tcgdex.net ...")

    session = requests.Session()
    session.headers.update(HEADERS)

    # Get the full list (fast, single request)
    r = session.get(f"{TCGDEX_BASE}/{lang}/sets", timeout=15)
    r.raise_for_status()
    summaries: list[dict] = r.json()
    print(f"  Found {len(summaries)} sets — fetching details in parallel ...")

    detail_map: dict[str, dict | None] = {}

    def _fetch(s: dict) -> tuple[str, dict | None]:
        return s["id"], fetch_set_detail(lang, s["id"], session)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch, s): s["id"] for s in summaries}
        done = 0
        for fut in as_completed(futures):
            sid, detail = fut.result()
            detail_map[sid] = detail
            done += 1
            if done % 20 == 0 or done == len(summaries):
                elapsed = time.time() - t0
                print(f"  {done}/{len(summaries)} details fetched ({elapsed:.1f}s)")

    result = []
    for s in summaries:
        rec = build_set_record(s, detail_map.get(s["id"]), lang, en_logo_map)
        result.append(rec)

    # Sort by releaseDate descending (newest first), matching EN sets.json order
    result.sort(key=lambda x: x.get("releaseDate", "") or "", reverse=True)

    # Deduplicate by ID (tcgdex sometimes returns the same set ID multiple times)
    seen_ids: set[str] = set()
    unique: list[dict] = []
    for rec in result:
        if rec["id"] not in seen_ids:
            seen_ids.add(rec["id"])
            unique.append(rec)
    if len(unique) < len(result):
        print(f"  Removed {len(result) - len(unique)} duplicate set IDs")
    print(f"  Done — {len(unique)} {label} sets ready.")
    return unique


def main():
    print("Fetching EN logo map from tcgdex.net ...")
    en_logo_map = get_en_logo_map()

    for lang in LANGS:
        sets = fetch_lang_sets(lang, en_logo_map)
        out_path = OUT_DIR / f"sets_{lang}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sets, f, ensure_ascii=False, indent=2)
        logo_count = sum(1 for s in sets if s["images"]["logo"])
        print(f"  Saved → {out_path} ({len(sets)} sets, {logo_count} with logos)")


if __name__ == "__main__":
    main()
