"""
fill_th_en_names_tcgdex.py — Fill English names for Thai cards and clean up
Thai card names by removing stage/type prefixes.

Strategy:
1. Strip Thai prefixes (พื้นฐาน/Basic, ร่าง 1/Stage 1, etc.) from card names
2. Cross-match with JA cards in our DB by set code + card number
3. For remaining cards, try TCGdex JA API (individual card by set+number) -> dexId -> PokeAPI
4. For SV-era cards, also try direct SV set lookup on TCGdex
"""

import io
import os
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))
session = requests.Session()
session.headers.update({"User-Agent": "Pokemon TCG EN name filler"})

TCGDEX_JA = "https://api.tcgdex.net/v2/ja"
POKEAPI = "https://pokeapi.co/api/v2/pokemon-species"

# Thai prefixes to strip from card names
TH_PREFIXES = [
    "พื้นฐาน",      # Basic
    "ร่าง 2",       # Stage 2
    "ร่าง 1",       # Stage 1
    "อื่น ๆ",       # Other (VMAX etc.)
    "เมก้า",        # Mega
    "ฟิวชัน",       # BREAK/Fusion
    "Restored ",    # Restored
    "Mega ",
    "MEGA ",
]

# Known Thai -> JA set code mappings
TH_TO_JA_MAP = {
    "SC1a": "S1W",
    "SC1b": "S1H",
    "SC3a": "S3",
    "SC3b": "S3a",
}

# Cache for PokeAPI lookups
_pokeapi_cache: dict[int, str] = {}


def strip_th_prefix(name: str) -> str:
    """Remove Thai stage/type prefixes from card names."""
    for prefix in TH_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def get_pokemon_name(dex_id: int) -> str:
    """Get English Pokemon name from PokeAPI by national dex number."""
    if dex_id in _pokeapi_cache:
        return _pokeapi_cache[dex_id]
    try:
        resp = session.get(f"{POKEAPI}/{dex_id}", timeout=10)
        if resp.status_code != 200:
            _pokeapi_cache[dex_id] = ""
            return ""
        data = resp.json()
        for entry in data.get("names", []):
            if entry.get("language", {}).get("name") == "en":
                name = entry["name"]
                _pokeapi_cache[dex_id] = name
                return name
    except Exception:
        pass
    _pokeapi_cache[dex_id] = ""
    return ""


def extract_suffix(name: str) -> str:
    """Extract Pokemon card suffix (ex, V, VMAX, VSTAR, GX, etc.)."""
    suffixes = [" VSTAR", " VMAX", " GX", " EX", " V", " ex"]
    for s in suffixes:
        if name.upper().endswith(s.upper()):
            return s
    # Check for Thai suffix patterns
    thai_suffixes = {
        "VSTAR": " VSTAR", "VMAX": " VMAX", "GX": " GX",
        "EX": " EX", "V": " V",
    }
    for key, val in thai_suffixes.items():
        if name.endswith(key):
            return val
    return ""


def fetch_en_via_tcgdex(set_code: str, number: str) -> str | None:
    """Fetch English name for a card from TCGdex JA via dexId -> PokeAPI."""
    for num_fmt in [number.zfill(3), number, number.lstrip("0") or "0"]:
        card_id = f"{set_code}-{num_fmt}"
        try:
            resp = session.get(f"{TCGDEX_JA}/cards/{card_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                dex_ids = data.get("dexId", [])
                ja_name = data.get("name", "")
                if dex_ids:
                    en_name = get_pokemon_name(dex_ids[0])
                    if en_name:
                        suffix = extract_suffix(ja_name)
                        return f"{en_name}{suffix}" if suffix else en_name
                return None  # Card found but no dexId (Trainer/Energy)
        except Exception:
            continue
    return None


def paginated_fetch(table: str, select: str, filters: dict, like_filters: dict = None) -> list[dict]:
    """Fetch all rows from a table with pagination."""
    rows: list[dict] = []
    offset = 0
    while True:
        q = sb.table(table).select(select)
        for k, v in filters.items():
            q = q.eq(k, v)
        if like_filters:
            for k, v in like_filters.items():
                q = q.like(k, v)
        data = q.range(offset, offset + 999).execute()
        if not data.data:
            break
        rows.extend(data.data)
        if len(data.data) < 1000:
            break
        offset += 1000
    return rows


def main():
    print("=" * 60)
    print("Cleaning Thai card names + filling English names")
    print("=" * 60)

    # ─── Step 1: Clean Thai names (strip prefixes) ───
    print("\nStep 1: Cleaning Thai card names (stripping prefixes)...")

    all_th_cards = paginated_fetch("cards", "id, name, number, set_id, name_en, supertype",
                                   {}, like_filters={"set_id": "%-th"})
    print(f"  Total Thai cards: {len(all_th_cards)}")

    name_updates = 0
    for card in all_th_cards:
        clean = strip_th_prefix(card["name"])
        if clean != card["name"]:
            sb.table("cards").update({"name": clean}).eq("id", card["id"]).execute()
            card["name"] = clean  # Update in-memory too
            name_updates += 1
            if name_updates % 100 == 0:
                print(f"  Cleaned {name_updates} names...", end="\r")

    print(f"  Cleaned {name_updates} card names")

    # ─── Step 2: Fill English names ───
    missing = [c for c in all_th_cards if not c.get("name_en")]
    print(f"\nStep 2: Filling English names for {len(missing)} cards...")

    # 2a: Load JA cards with name_en from DB
    print("  Loading JA name_en lookup...")
    ja_cards = paginated_fetch("cards", "number, name_en, set_id, name",
                               {}, like_filters={"set_id": "%-ja"})
    ja_with_en = [c for c in ja_cards if c.get("name_en")]

    # Build lookup: (set_code, number) -> name_en
    ja_lookup: dict[tuple[str, str], str] = {}
    for c in ja_with_en:
        code = c["set_id"].replace("-ja", "")
        num = c["number"]
        ja_lookup[(code, num)] = c["name_en"]
        ja_lookup[(code, num.lstrip("0") or "0")] = c["name_en"]
        ja_lookup[(code, num.zfill(3))] = c["name_en"]

    # Also build ja_name -> name_en for fuzzy matching
    ja_name_to_en: dict[str, str] = {}
    for c in ja_with_en:
        if c.get("name_en"):
            ja_name_to_en[c["name"]] = c["name_en"]

    print(f"  {len(ja_with_en)} JA cards with name_en, {len(ja_name_to_en)} unique name mappings")

    # 2b: Cross-match by set code + number
    en_updates: list[tuple[str, str]] = []
    still_missing: list[dict] = []

    for card in missing:
        code = card["set_id"].replace("-th", "")
        ja_code = TH_TO_JA_MAP.get(code, code)
        num = card["number"]
        en = (
            ja_lookup.get((ja_code, num))
            or ja_lookup.get((ja_code, num.lstrip("0") or "0"))
            or ja_lookup.get((ja_code, num.zfill(3)))
        )
        if en:
            en_updates.append((card["id"], en))
        else:
            still_missing.append({**card, "_ja_code": ja_code})

    print(f"  DB cross-match: {len(en_updates)} found, {len(still_missing)} remaining")

    # 2c: Try TCGdex for remaining cards
    if still_missing:
        print(f"  Trying TCGdex for {len(still_missing)} remaining cards...")
        tcgdex_found = 0
        for i, card in enumerate(still_missing):
            en = fetch_en_via_tcgdex(card["_ja_code"], card["number"])
            if en:
                en_updates.append((card["id"], en))
                tcgdex_found += 1
            if (i + 1) % 50 == 0:
                print(f"    Progress: {i+1}/{len(still_missing)} (found {tcgdex_found})", end="\r")
            time.sleep(0.05)
        print(f"    TCGdex: found {tcgdex_found}/{len(still_missing)}                ")

    # ─── Step 3: Apply English name updates ───
    if en_updates:
        print(f"\nStep 3: Applying {len(en_updates)} English name updates...")
        for i, (card_id, name_en) in enumerate(en_updates):
            sb.table("cards").update({"name_en": name_en}).eq("id", card_id).execute()
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(en_updates)}", end="\r")
        print(f"  {len(en_updates)}/{len(en_updates)} done")

    # ─── Summary ───
    final_missing = (
        sb.table("cards")
        .select("id", count="exact", head=True)
        .like("set_id", "%-th")
        .eq("name_en", "")
        .execute()
    )
    print(f"\nSummary:")
    print(f"  Names cleaned: {name_updates}")
    print(f"  English names filled: {len(en_updates)}")
    print(f"  Still missing name_en: {final_missing.count}")
    print("\nDone!")


if __name__ == "__main__":
    main()
