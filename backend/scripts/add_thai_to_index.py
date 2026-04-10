"""
Append Thai cards to the existing on-device visual match index.

The current index (`public/card_index_mobile.bin` + `card_index_meta.json`)
covers ~20k English cards from pokemontcg.io. This script:

  1. Loads the existing quantized EN index and dequantizes it back to floats.
  2. Loads Thai cards from `backend/th_cards_2024_2025.json`.
  3. Skips any Thai cards already present (safe to re-run).
  4. Downloads + embeds each Thai card image with MobileNetV3-Small (576-D),
     the same feature extractor used for the EN index.
  5. Concatenates EN + TH features, re-quantizes per-dimension to uint8,
     and writes a new combined `card_index_mobile.bin` + `card_index_meta.json`.

Notes on the dequant→requant round-trip: per-dim uint8 quantization loses
roughly one part in ~256, which is well below the noise floor of a photo
scan. Cosine-similarity match quality is unaffected in practice.

Usage (from the project root, with torch + torchvision + requests installed):

    python -m backend.scripts.add_thai_to_index

Expected runtime: ~10-20 minutes depending on network for the 3,143 image
downloads. Images are cached in `backend/_image_cache/`, so re-runs are fast.
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
# Feature extractor — must match backend/training/export_mobile_onnx.py
# ---------------------------------------------------------------------------

class MobileFeatureExtractor(nn.Module):
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
# Load existing index (dequantized) + metadata
# ---------------------------------------------------------------------------

def load_existing_index() -> tuple[np.ndarray, list[dict]]:
    if not INDEX_BIN.exists() or not INDEX_META.exists():
        raise FileNotFoundError(
            f"Expected {INDEX_BIN} and {INDEX_META}. Run export_mobile_onnx first."
        )

    with open(INDEX_BIN, "rb") as f:
        n_cards, dim = struct.unpack("<II", f.read(8))
        mins = np.frombuffer(f.read(dim * 4), dtype=np.float32)
        maxs = np.frombuffer(f.read(dim * 4), dtype=np.float32)
        quantized = np.frombuffer(f.read(n_cards * dim), dtype=np.uint8)

    if dim != FEATURE_DIM:
        raise ValueError(f"Index dim {dim} != expected {FEATURE_DIM}")

    quantized = quantized.reshape(n_cards, dim).astype(np.float32)
    ranges = (maxs - mins).copy()
    ranges[ranges == 0] = 1.0
    features = mins + (quantized / 255.0) * ranges  # (N, dim)

    with open(INDEX_META, encoding="utf-8") as f:
        metadata = json.load(f)

    if len(metadata) != n_cards:
        raise ValueError(
            f"Meta length {len(metadata)} != index cards {n_cards}"
        )

    print(f"[existing] {n_cards} cards loaded, {dim}-D features")
    return features, metadata

# ---------------------------------------------------------------------------
# Thai card loading
# ---------------------------------------------------------------------------

def normalize_thai_card(card: dict) -> dict:
    """Shape a Thai card entry to match the EN metadata schema."""
    return {
        "id": card["id"],
        "name": card.get("name", ""),
        "number": card.get("number", ""),
        "set_id": card.get("set_id", ""),
        "set_name": card.get("set_name", card.get("set_id", "")),
        "rarity": card.get("rarity", ""),
        "image_small": card.get("image_small", ""),
        "image_large": card.get("image_large", card.get("image_small", "")),
        "supertype": card.get("supertype", ""),
        "subtypes": card.get("subtypes", []),
        "hp": card.get("hp", ""),
        "artist": card.get("artist", ""),
    }


def load_thai_cards(existing_ids: set[str]) -> list[dict]:
    if not TH_CARDS_JSON.exists():
        raise FileNotFoundError(f"Missing {TH_CARDS_JSON}")
    with open(TH_CARDS_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    new = [normalize_thai_card(c) for c in raw if c["id"] not in existing_ids]
    print(f"[thai] {len(raw)} total, {len(new)} new (not already indexed)")
    return new

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
    except Exception as err:
        print(f"  ! failed {url}: {err}")
        return None


def embed_cards(cards: list[dict], model: MobileFeatureExtractor) -> tuple[np.ndarray, list[dict]]:
    n = len(cards)
    features = np.zeros((n, FEATURE_DIM), dtype=np.float32)
    valid_mask = np.zeros(n, dtype=bool)

    start = time.time()
    failed = 0

    for batch_start in range(0, n, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, n)
        batch = cards[batch_start:batch_end]
        tensors = []
        idxs = []

        for j, card in enumerate(batch):
            img = load_image(card.get("image_small", ""))
            if img is None:
                failed += 1
                continue
            tensors.append(TRANSFORM(img))
            idxs.append(batch_start + j)

        if not tensors:
            continue

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
        print(f"  {done}/{n} embedded ({failed} failed, {rate:.1f}/s, ETA {eta:.0f}s)")

    kept_features = features[valid_mask]
    kept_cards = [c for c, keep in zip(cards, valid_mask) if keep]
    print(f"[thai] {len(kept_cards)} cards successfully embedded ({failed} failed)")
    return kept_features, kept_cards

# ---------------------------------------------------------------------------
# Quantize + write
# ---------------------------------------------------------------------------

def write_combined_index(features: np.ndarray, metadata: list[dict]) -> None:
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
    print(f"[write] {INDEX_BIN.name} ({bin_mb:.1f} MB), {INDEX_META.name} ({meta_mb:.1f} MB)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Appending Thai cards to visual match index")
    print("=" * 60)

    en_features, en_meta = load_existing_index()
    existing_ids = {c["id"] for c in en_meta}

    th_cards = load_thai_cards(existing_ids)
    if not th_cards:
        print("Nothing to do — all Thai cards already indexed.")
        return

    print("Loading MobileNetV3-Small...")
    model = MobileFeatureExtractor()
    model.eval()

    th_features, th_meta = embed_cards(th_cards, model)
    if len(th_meta) == 0:
        print("No Thai cards embedded successfully. Aborting.")
        return

    combined_features = np.concatenate([en_features, th_features], axis=0)
    combined_meta = en_meta + th_meta

    print(f"[combined] {len(combined_meta)} cards total "
          f"(EN: {len(en_meta)}, TH: {len(th_meta)})")

    write_combined_index(combined_features, combined_meta)
    print("Done. Rebuild the web bundle to pick up the new index.")


if __name__ == "__main__":
    main()
