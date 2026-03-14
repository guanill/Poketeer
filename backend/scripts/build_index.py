"""
build_index.py — build a local card feature index from the official
Pokémon TCG data GitHub repo.  No API key required.

Data source (MIT-licensed community data, maintained by pokemontcg.io team):
  https://github.com/PokemonTCG/pokemon-tcg-data

Card images come from the open CDN: images.pokemontcg.io
(no authentication required for image downloads)

Usage:
    python build_index.py                  # index every English card
    python build_index.py --sets base1 xy1 # only index specific sets
    python build_index.py --limit 200      # quick smoke-test

Output:  backend/card_index.npz
         backend/card_names.json   ← used by OCR matcher
"""

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

# Force UTF-8 output on Windows so unicode chars in print() don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import requests
from tqdm import tqdm

# Add backend root to path so we can import server modules
sys.path.insert(0, str(BACKEND_DIR))
from model import extract_features_from_url

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_ZIP_URL = (
    "https://github.com/PokemonTCG/pokemon-tcg-data/"
    "archive/refs/heads/master.zip"
)
BACKEND_DIR = Path(__file__).resolve().parent.parent
INDEX_PATH = BACKEND_DIR / "card_index.npz"
NAMES_PATH = BACKEND_DIR / "card_names.json"
SETS_PATH  = BACKEND_DIR / "sets.json"
DATA_CACHE = BACKEND_DIR / "_tcg_data_cache"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def download_data_zip() -> None:
    """Download & cache the pokemontcg-data GitHub repo ZIP."""
    DATA_CACHE.mkdir(exist_ok=True)
    zip_path = DATA_CACHE / "master.zip"

    print("Downloading Pokémon TCG card data from GitHub …")
    print(f"  {DATA_ZIP_URL}")
    resp = requests.get(DATA_ZIP_URL, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    with open(zip_path, "wb") as f, tqdm(
        desc="  Downloading", total=total, unit="B", unit_scale=True
    ) as bar:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            bar.update(len(chunk))

    print("  Extracting …")
    with zipfile.ZipFile(zip_path) as zf:
        all_members = zf.namelist()
        # Filter to only cards/en JSON files to keep extraction fast
        members = [
            m for m in all_members
            if "cards/en/" in m.replace("\\", "/") and m.endswith(".json")
        ]
        # Fall back to full extraction if filter matched nothing
        if not members:
            members = all_members
        zf.extractall(DATA_CACHE, members=members)

    print(f"  Cached to {DATA_CACHE}")


def load_all_cards(set_ids: list[str] | None = None) -> list[dict]:
    """Load card records from the cached JSON files."""
    # Find the extracted directory — search several common patterns
    roots = (
        list(DATA_CACHE.glob("*/data/cards/en")) +
        list(DATA_CACHE.glob("**/cards/en"))
    )
    if not roots:
        download_data_zip()
        roots = (
            list(DATA_CACHE.glob("*/data/cards/en")) +
            list(DATA_CACHE.glob("**/cards/en"))
        )

    if not roots:
        print("ERROR: Could not find card data after download.")
        sys.exit(1)

    cards_dir = roots[0]
    json_files = sorted(cards_dir.glob("*.json"))

    if set_ids:
        json_files = [f for f in json_files if f.stem in set_ids]
        print(f"  Filtering to sets: {[f.stem for f in json_files]}")

    all_cards: list[dict] = []
    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            cards = json.load(f)
        for card in cards:
            # Normalise: attach set info
            set_obj = card.get("set", {})
            card["_set_id"] = set_obj.get("id", jf.stem)
            card["_set_name"] = set_obj.get("name", jf.stem)
        all_cards.extend(cards)

    print(f"  Loaded {len(all_cards)} cards from {len(json_files)} set(s).")
    return all_cards


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def build_index(set_ids: list[str] | None = None, limit: int | None = None) -> None:
    print("Loading card data …")
    cards = load_all_cards(set_ids)

    if limit:
        cards = cards[:limit]
        print(f"  Limiting to {limit} cards for testing.")

    feature_list: list[np.ndarray] = []
    metadata: list[dict] = []
    name_records: list[dict] = []   # for OCR matcher (no images needed)
    sets_seen: dict[str, dict] = {} # for sets.json

    print(f"\nExtracting features from {len(cards)} cards …")
    for card in tqdm(cards, unit="card"):
        img_url = card.get("images", {}).get("small", "")
        if not img_url:
            continue

        features = extract_features_from_url(img_url)

        meta = {
            "id": card["id"],
            "name": card["name"],
            "number": card.get("number", ""),
            "set_id": card["_set_id"],
            "set_name": card["_set_name"],
            "rarity": card.get("rarity", ""),
            "image_small": img_url,
            "image_large": card.get("images", {}).get("large", ""),
            "supertype": card.get("supertype", ""),
            "subtypes": card.get("subtypes") or [],
            "types": card.get("types") or [],
            "hp": card.get("hp", ""),
            "artist": card.get("artist", ""),
        }

        # Always add to name list (OCR uses this, no image needed)
        name_records.append(meta)

        # Collect rich set metadata (logo/symbol URLs live on the set object)
        if card["_set_id"] not in sets_seen:
            set_obj = card.get("set", {})
            sets_seen[card["_set_id"]] = {
                "id": card["_set_id"],
                "name": card["_set_name"],
                "series": set_obj.get("series", ""),
                "printedTotal": set_obj.get("printedTotal", 0),
                "total": set_obj.get("total", 0),
                "releaseDate": set_obj.get("releaseDate", ""),
                "images": set_obj.get("images", {"symbol": "", "logo": ""}),
            }

        if features is not None:
            feature_list.append(features)
            metadata.append(meta)

        time.sleep(0.02)   # gentle on the image CDN

    # Save OCR name list
    with open(NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump(name_records, f)
    print(f"Saved {len(name_records)} card name records -> {NAMES_PATH}")

    # Save sets metadata (logo / symbol / release date etc.)
    sets_list = sorted(sets_seen.values(), key=lambda s: s.get("releaseDate", ""))
    with open(SETS_PATH, "w", encoding="utf-8") as f:
        json.dump(sets_list, f)
    print(f"Saved {len(sets_list)} set records -> {SETS_PATH}")

    # Save visual feature index
    if feature_list:
        features_matrix = np.stack(feature_list, axis=0)
        np.savez_compressed(
            str(INDEX_PATH),
            features=features_matrix,
            metadata=json.dumps(metadata).encode("utf-8"),
        )
        print(f"Saved visual index ({len(metadata)} cards) -> {INDEX_PATH}")
    else:
        print("WARNING: No visual features extracted (image CDN unreachable?).")
        print("OCR-only matching will still work.")

    print("\nDone!")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build local Pokémon card index (no API key required)"
    )
    parser.add_argument("--sets", nargs="*",
                        help="Set IDs to index, e.g. --sets base1 jungle (default: all)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max cards to process (for quick tests)")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-download card data even if cache exists")
    args = parser.parse_args()

    if args.refresh and DATA_CACHE.exists():
        import shutil
        shutil.rmtree(DATA_CACHE)
        print("Cache cleared.")

    build_index(set_ids=args.sets, limit=args.limit)
