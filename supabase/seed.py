"""
seed.py — Populate Supabase tables from existing backend data files.

Reads:
  backend/sets.json           → sets table
  backend/sets_ja.json        → sets table (language='ja')
  backend/sets_th.json        → sets table (language='th')
  backend/card_names.json     → cards table
  backend/card_index.npz      → card_embeddings table (512-D CardEmbedder)

Usage:
    pip install supabase python-dotenv numpy
    python supabase/seed.py

Environment:
    SUPABASE_URL         — project URL
    SUPABASE_SERVICE_KEY — service-role key (NOT the anon key)
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env.seed")
    print("       Use the service-role key (Settings > API > service_role)")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BATCH = 500  # Supabase upsert batch size


def upsert_batch(table: str, rows: list[dict], batch_size: int = BATCH):
    """Upsert rows in batches, printing progress."""
    total = len(rows)
    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        sb.table(table).upsert(batch).execute()
        done = min(i + batch_size, total)
        print(f"  {table}: {done}/{total}", end="\r")
    print(f"  {table}: {total}/{total} done")


# ---------------------------------------------------------------------------
# 1. Sets
# ---------------------------------------------------------------------------

def seed_sets():
    print("\n[1/4] Seeding sets...")

    all_sets: list[dict] = []

    for path, lang in [
        (BACKEND / "sets.json", "en"),
        (BACKEND / "sets_ja.json", "ja"),
        (BACKEND / "sets_th.json", "th"),
    ]:
        if not path.exists():
            print(f"  Skipping {path.name} (not found)")
            continue
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        for s in raw:
            images = s.get("images", {})
            # Make IDs unique per language to avoid PK conflicts
            set_id = s["id"] if lang == "en" else f"{s['id']}-{lang}"
            all_sets.append({
                "id": set_id,
                "name": s.get("name", ""),
                "series": s.get("series", ""),
                "printed_total": s.get("printedTotal", 0),
                "total": s.get("total", 0),
                "release_date": s.get("releaseDate", ""),
                "language": lang,
                "symbol_url": images.get("symbol", ""),
                "logo_url": images.get("logo", ""),
            })
        print(f"  Loaded {len(raw)} {lang} sets from {path.name}")

    if all_sets:
        upsert_batch("sets", all_sets)


# ---------------------------------------------------------------------------
# 2. Cards
# ---------------------------------------------------------------------------

def seed_cards():
    print("\n[2/4] Seeding cards...")

    cards_path = BACKEND / "card_names.json"
    if not cards_path.exists():
        print(f"  ERROR: {cards_path} not found")
        return

    with open(cards_path, encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for c in raw:
        rows.append({
            "id": c["id"],
            "name": c.get("name", ""),
            "number": c.get("number", ""),
            "set_id": c.get("set_id", ""),
            "rarity": c.get("rarity", ""),
            "image_small": c.get("image_small", ""),
            "image_large": c.get("image_large", ""),
            "supertype": c.get("supertype", ""),
            "subtypes": c.get("subtypes") or [],
            "hp": c.get("hp", ""),
            "artist": c.get("artist", ""),
            "types": c.get("types") or [],
        })

    print(f"  Loaded {len(rows)} cards")
    upsert_batch("cards", rows)


# ---------------------------------------------------------------------------
# 3. Embeddings
# ---------------------------------------------------------------------------

def seed_embeddings():
    print("\n[3/4] Seeding card embeddings...")

    index_path = BACKEND / "card_index.npz"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — skipping embeddings")
        return

    data = np.load(str(index_path), allow_pickle=False)
    features = data["features"]  # (N, dim)
    metadata = json.loads(data["metadata"].tobytes().decode("utf-8"))

    n, dim = features.shape
    print(f"  Loaded {n} embeddings ({dim}-D)")

    # The DB column is vector(576) to match the on-device ONNX model.
    # If the local index uses a different dimension, skip seeding.
    EXPECTED_DIM = 576
    if dim != EXPECTED_DIM:
        print(f"  SKIP: index is {dim}-D but DB expects {EXPECTED_DIM}-D")
        print(f"  Re-export with: python -m backend.training.export_mobile_onnx")
        return

    # pgvector expects the embedding as a string like "[0.1, 0.2, ...]"
    rows = []
    for i in range(n):
        card_id = metadata[i]["id"]
        vec = features[i].tolist()
        # Format as pgvector string
        vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
        rows.append({
            "card_id": card_id,
            "embedding": vec_str,
        })

    # Embeddings are big — use smaller batches
    upsert_batch("card_embeddings", rows, batch_size=200)


# ---------------------------------------------------------------------------
# 4. Prices cache (optional)
# ---------------------------------------------------------------------------

def seed_prices():
    print("\n[4/4] Seeding prices cache...")

    prices_path = BACKEND / "prices_cache.json"
    if not prices_path.exists():
        print(f"  Skipping prices (not found)")
        return

    with open(prices_path, encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for card_id, entry in raw.items():
        rows.append({
            "card_id": card_id,
            "market_price": entry.get("market"),
            "failed": entry.get("failed", False),
        })

    print(f"  Loaded {len(rows)} price entries")
    if rows:
        upsert_batch("prices_cache", rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Seeding Supabase from local backend data")
    print(f"  URL: {SUPABASE_URL}")
    print("=" * 60)

    start = time.time()
    seed_sets()
    seed_cards()
    seed_embeddings()
    seed_prices()

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
