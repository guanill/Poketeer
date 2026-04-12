"""
Rebuild the on-device visual match index from scratch with EN + TH cards.

The previously-shipped `public/card_index_mobile.bin` was 512-D but the
`public/card_model.onnx` feature extractor outputs 576-D. Those dimensions
don't match, so `visualMatchService.init()` fails its dim check on every
load and silently disables visual matching. This script fixes that by
re-embedding every card (EN from `card_index_meta.json`, TH from
`backend/th_cards_2024_2025.json`) using MobileNetV3-Small and writing a
fresh 576-D quantized index.

Source metadata:
  - EN: `public/card_index_meta.json`       (20,026 cards)
  - TH: `backend/th_cards_2024_2025.json`   (3,143 cards)

Outputs (overwritten):
  - `public/card_index_mobile.bin`
  - `public/card_index_meta.json`

Images are cached in `backend/_image_cache/` so re-runs after network
failures don't re-download successful cards.

Usage (from project root):
    python -m backend.scripts.add_thai_to_index

Expected runtime: 30-90 minutes on a cold cache (limited by card image
downloads from images.pokemontcg.io and asia.pokemon-card.com).
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import time
from pathlib import Path

import numpy as np
import requests
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
PUBLIC_DIR = PROJECT_ROOT / "public"

INDEX_BIN = PUBLIC_DIR / "card_index_mobile.bin"
INDEX_META = PUBLIC_DIR / "card_index_meta.json"
TH_CARDS_JSON = BACKEND_DIR / "th_cards_2024_2025.json"
IMAGE_CACHE = BACKEND_DIR / "_image_cache"
IMAGE_CACHE.mkdir(exist_ok=True)

FEATURE_DIM = 576
INPUT_SIZE = 224
BATCH_SIZE = 32

# ---------------------------------------------------------------------------
# Feature extractor — must match what card_model.onnx in public/ produces
# ---------------------------------------------------------------------------

class MobileFeatureExtractor(nn.Module):
    """MobileNetV3-Small as L2-normalised feature extractor (576-D)."""
    def __init__(self):
        super().__init__()
        weights = models.MobileNet_V3_Small_Weights.DEFAULT
        backbone = models.mobilenet_v3_small(weights=weights)
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        self.flatten = nn.Flatten()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.avgpool(x)
        x = self.flatten(x)
        return torch.nn.functional.normalize(x, p=2, dim=1)


TRANSFORM = T.Compose([
    T.Resize((INPUT_SIZE, INPUT_SIZE)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# ---------------------------------------------------------------------------
# Source metadata loaders
# ---------------------------------------------------------------------------

EN_META_FIELDS = (
    "id", "name", "number", "set_id", "set_name", "rarity",
    "image_small", "image_large", "supertype", "subtypes", "hp", "artist",
)


def normalize_card(card: dict) -> dict:
    """Shape a card entry to the metadata schema visualMatchService expects."""
    return {
        "id": card.get("id", ""),
        "name": card.get("name", ""),
        "number": card.get("number", ""),
        "set_id": card.get("set_id", ""),
        "set_name": card.get("set_name", card.get("set_id", "")),
        "rarity": card.get("rarity", ""),
        "image_small": card.get("image_small", ""),
        "image_large": card.get("image_large", card.get("image_small", "")),
        "supertype": card.get("supertype", ""),
        "subtypes": card.get("subtypes", []) or [],
        "hp": card.get("hp", ""),
        "artist": card.get("artist", ""),
    }


def load_en_cards() -> list[dict]:
    if not INDEX_META.exists():
        raise FileNotFoundError(f"Missing {INDEX_META}")
    with open(INDEX_META, encoding="utf-8") as f:
        raw = json.load(f)
    cards = [normalize_card(c) for c in raw]
    print(f"[en] {len(cards)} cards loaded from {INDEX_META.name}")
    return cards


def load_th_cards() -> list[dict]:
    if not TH_CARDS_JSON.exists():
        raise FileNotFoundError(f"Missing {TH_CARDS_JSON}")
    with open(TH_CARDS_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    cards = [normalize_card(c) for c in raw]
    print(f"[th] {len(cards)} cards loaded from {TH_CARDS_JSON.name}")
    return cards

# ---------------------------------------------------------------------------
# Image download (cached) + batched embedding
# ---------------------------------------------------------------------------

def load_image(url: str) -> Image.Image | None:
    if not url:
        return None
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = IMAGE_CACHE / f"{url_hash}.img"
    if cache_path.exists():
        try:
            return Image.open(cache_path).convert("RGB")
        except Exception:
            cache_path.unlink(missing_ok=True)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        cache_path.write_bytes(resp.content)
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None


def embed_cards(cards: list[dict], model: MobileFeatureExtractor,
                label: str) -> tuple[np.ndarray, list[dict]]:
    n = len(cards)
    features = np.zeros((n, FEATURE_DIM), dtype=np.float32)
    valid_mask = np.zeros(n, dtype=bool)

    print(f"[{label}] embedding {n} cards...")
    start = time.time()
    failed = 0

    for batch_start in range(0, n, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, n)
        batch = cards[batch_start:batch_end]
        tensors: list[torch.Tensor] = []
        idxs: list[int] = []

        for j, card in enumerate(batch):
            img = load_image(card.get("image_small", ""))
            if img is None:
                failed += 1
                continue
            tensors.append(TRANSFORM(img))
            idxs.append(batch_start + j)

        if tensors:
            batch_tensor = torch.stack(tensors)
            with torch.no_grad():
                emb = model(batch_tensor).numpy()
            for local_i, global_i in enumerate(idxs):
                features[global_i] = emb[local_i]
                valid_mask[global_i] = True

        done = batch_end
        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (n - done) / rate if rate > 0 else 0
        if done % (BATCH_SIZE * 5) == 0 or done == n:
            print(f"  [{label}] {done}/{n} "
                  f"({failed} failed, {rate:.1f}/s, ETA {eta:.0f}s)")

    kept_features = features[valid_mask]
    kept_cards = [c for c, keep in zip(cards, valid_mask) if keep]
    print(f"[{label}] {len(kept_cards)} embedded, {failed} failed")
    return kept_features, kept_cards

# ---------------------------------------------------------------------------
# Quantize + write
# ---------------------------------------------------------------------------

def write_index(features: np.ndarray, metadata: list[dict]) -> None:
    n_cards, dim = features.shape
    mins = features.min(axis=0).astype(np.float32)
    maxs = features.max(axis=0).astype(np.float32)
    ranges = (maxs - mins).copy()
    ranges[ranges == 0] = 1.0
    quantized = ((features - mins) / ranges * 255).clip(0, 255).astype(np.uint8)

    with open(INDEX_BIN, "wb") as f:
        f.write(struct.pack("<II", n_cards, dim))
        f.write(mins.tobytes())
        f.write(maxs.tobytes())
        f.write(quantized.tobytes())

    with open(INDEX_META, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)

    bin_mb = INDEX_BIN.stat().st_size / 1e6
    meta_mb = INDEX_META.stat().st_size / 1e6
    print(f"[write] {INDEX_BIN.name} ({bin_mb:.1f} MB), "
          f"{INDEX_META.name} ({meta_mb:.1f} MB)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Rebuilding visual match index (EN + TH, 576-D)")
    print("=" * 60)

    en_cards = load_en_cards()
    th_cards = load_th_cards()

    # De-duplicate in case an EN-meta entry collides with a TH id (shouldn't)
    en_ids = {c["id"] for c in en_cards}
    th_cards = [c for c in th_cards if c["id"] not in en_ids]

    print("Loading MobileNetV3-Small (ImageNet weights)...")
    model = MobileFeatureExtractor()
    model.eval()

    en_features, en_meta = embed_cards(en_cards, model, "en")
    th_features, th_meta = embed_cards(th_cards, model, "th")

    if len(en_meta) == 0 and len(th_meta) == 0:
        print("No cards embedded. Aborting.")
        return

    combined_features = np.concatenate(
        [f for f in (en_features, th_features) if len(f) > 0], axis=0,
    )
    combined_meta = en_meta + th_meta

    print(f"[combined] {len(combined_meta)} cards total "
          f"(EN: {len(en_meta)}, TH: {len(th_meta)}), "
          f"{combined_features.shape[1]}-D")

    write_index(combined_features, combined_meta)
    print("Done. Rebuild the web bundle to pick up the new index.")


if __name__ == "__main__":
    main()
