"""
DEPRECATED — use backend/training/export_mobile_onnx.py instead.

This script applies PCA reduction which requires loading PCA components at
inference time in the web/mobile client.  The visualMatchService.ts client
does NOT apply PCA projection, so using this script to build the index
causes a feature-space mismatch and broken visual matching.

Use `python -m backend.training.export_mobile_onnx` which stores the raw
MobileNetV3 features (576-D, quantized to uint8) without PCA, matching
what the ONNX model outputs at inference time.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import io
import onnx
import requests

# Paths
BACKEND = Path(__file__).resolve().parent.parent
PUBLIC = BACKEND.parent / "public"
PUBLIC.mkdir(exist_ok=True)

ONNX_PATH = PUBLIC / "card_model.onnx"
INDEX_PATH = PUBLIC / "card_index_mobile.bin"
META_PATH = PUBLIC / "card_index_meta.json"
PCA_PATH = PUBLIC / "pca_components.bin"

# Existing index for card metadata
EXISTING_INDEX = BACKEND / "card_index.npz"
CARD_NAMES = BACKEND / "card_names.json"

INPUT_SIZE = 224
FEATURE_DIM = 576  # MobileNetV3-Small output
PCA_DIM = 256      # Reduced dimension
BATCH_SIZE = 64

# ---------------------------------------------------------------------------
# Step 1: Export MobileNetV3-Small to ONNX
# ---------------------------------------------------------------------------

def export_model():
    print("[1/4] Exporting MobileNetV3-Small to ONNX...")

    weights = models.MobileNet_V3_Small_Weights.DEFAULT
    base = models.mobilenet_v3_small(weights=weights)

    # Remove classifier, keep features + adaptive pool
    # Output: (batch, 576)
    class FeatureExtractor(nn.Module):
        def __init__(self, base_model):
            super().__init__()
            self.features = base_model.features
            self.avgpool = base_model.avgpool

        def forward(self, x):
            x = self.features(x)
            x = self.avgpool(x)
            x = x.flatten(1)
            # L2 normalize
            x = x / (x.norm(dim=1, keepdim=True) + 1e-8)
            return x

    model = FeatureExtractor(base)
    model.eval()

    dummy = torch.randn(1, 3, INPUT_SIZE, INPUT_SIZE)

    torch.onnx.export(
        model, dummy, str(ONNX_PATH),
        input_names=["image"],
        output_names=["features"],
        dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}},
        opset_version=13,
    )

    # Verify
    onnx_model = onnx.load(str(ONNX_PATH))
    onnx.checker.check_model(onnx_model)

    size_mb = ONNX_PATH.stat().st_size / 1024 / 1024
    print(f"   Model exported: {ONNX_PATH.name} ({size_mb:.1f} MB)")

    return model

# ---------------------------------------------------------------------------
# Step 2: Extract features for all cards
# ---------------------------------------------------------------------------

TRANSFORM = transforms.Compose([
    transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

def download_image(url: str, timeout=10) -> Image.Image | None:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None

def extract_features_batch(model, images: list[Image.Image]) -> np.ndarray:
    tensors = torch.stack([TRANSFORM(img) for img in images])
    with torch.inference_mode():
        features = model(tensors)
    return features.numpy()

def build_features(model):
    print("[2/4] Extracting features for all cards...")

    # Load card metadata
    with open(CARD_NAMES, encoding="utf-8") as f:
        cards = json.load(f)

    total = len(cards)
    print(f"   {total} cards to process")

    all_features = []
    valid_cards = []

    batch_images = []
    batch_cards = []

    start = time.time()
    processed = 0
    failed = 0

    for i, card in enumerate(cards):
        url = card.get("image_small", "")
        if not url:
            failed += 1
            continue

        img = download_image(url)
        if img is None:
            failed += 1
            continue

        batch_images.append(img)
        batch_cards.append(card)

        if len(batch_images) >= BATCH_SIZE or i == total - 1:
            features = extract_features_batch(model, batch_images)
            all_features.append(features)
            valid_cards.extend(batch_cards)
            processed += len(batch_images)

            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"   {processed}/{total} done ({failed} failed) "
                  f"[{rate:.1f} cards/s, ETA {eta:.0f}s]", end="\r")

            batch_images = []
            batch_cards = []

    print(f"\n   {processed} cards processed, {failed} failed")

    features_matrix = np.vstack(all_features)  # (N, 576)
    return features_matrix, valid_cards

# ---------------------------------------------------------------------------
# Step 3: PCA reduction + uint8 quantization
# ---------------------------------------------------------------------------

def compress_index(features: np.ndarray):
    print(f"[3/4] PCA {features.shape[1]}D -> {PCA_DIM}D + uint8 quantization...")

    from sklearn.decomposition import PCA

    # Fit PCA
    pca = PCA(n_components=PCA_DIM)
    reduced = pca.fit_transform(features)  # (N, PCA_DIM)

    explained = pca.explained_variance_ratio_.sum() * 100
    print(f"   PCA explained variance: {explained:.1f}%")

    # Save PCA components for inference-time projection
    # components: (PCA_DIM, FEATURE_DIM), mean: (FEATURE_DIM,)
    components = pca.components_.astype(np.float32)  # (256, 576)
    mean = pca.mean_.astype(np.float32)  # (576,)

    pca_data = np.concatenate([
        mean,           # 576 floats
        components.flatten(),  # 256*576 floats
    ]).astype(np.float32)
    pca_data.tofile(str(PCA_PATH))
    pca_size = PCA_PATH.stat().st_size / 1024 / 1024
    print(f"   PCA components saved: {PCA_PATH.name} ({pca_size:.2f} MB)")

    # Quantize reduced features to uint8
    # Per-dimension min/max for dequantization
    mins = reduced.min(axis=0).astype(np.float32)   # (PCA_DIM,)
    maxs = reduced.max(axis=0).astype(np.float32)   # (PCA_DIM,)
    ranges = maxs - mins
    ranges[ranges == 0] = 1  # avoid div by zero

    quantized = ((reduced - mins) / ranges * 255).clip(0, 255).astype(np.uint8)

    # Save: header (N, PCA_DIM as uint32) + mins + maxs + quantized data
    N = quantized.shape[0]
    header = np.array([N, PCA_DIM], dtype=np.uint32)

    with open(INDEX_PATH, "wb") as f:
        f.write(header.tobytes())       # 8 bytes
        f.write(mins.tobytes())         # PCA_DIM * 4 bytes
        f.write(maxs.tobytes())         # PCA_DIM * 4 bytes
        f.write(quantized.tobytes())    # N * PCA_DIM bytes

    index_size = INDEX_PATH.stat().st_size / 1024 / 1024
    print(f"   Index saved: {INDEX_PATH.name} ({index_size:.2f} MB)")

    return quantized

# ---------------------------------------------------------------------------
# Step 4: Save metadata
# ---------------------------------------------------------------------------

def save_metadata(cards: list[dict]):
    print("[4/4] Saving metadata...")

    # Only keep fields needed for scan results
    meta = []
    for card in cards:
        meta.append({
            "id": card["id"],
            "name": card["name"],
            "number": card.get("number", ""),
            "set_id": card.get("set_id", ""),
            "set_name": card.get("set_name", ""),
            "rarity": card.get("rarity", ""),
            "image_small": card.get("image_small", ""),
            "image_large": card.get("image_large", ""),
            "supertype": card.get("supertype", ""),
            "subtypes": card.get("subtypes", []),
            "hp": card.get("hp", ""),
            "artist": card.get("artist", ""),
        })

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, separators=(",", ":"))

    meta_size = META_PATH.stat().st_size / 1024 / 1024
    print(f"   Metadata saved: {META_PATH.name} ({meta_size:.2f} MB)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Building mobile card recognition index")
    print("=" * 60)

    start = time.time()

    model = export_model()
    features, cards = build_features(model)
    compress_index(features)
    save_metadata(cards)

    elapsed = time.time() - start

    print()
    print("=" * 60)
    total_mb = sum(
        p.stat().st_size for p in [ONNX_PATH, INDEX_PATH, META_PATH, PCA_PATH]
    ) / 1024 / 1024
    print(f"Total bundle size: {total_mb:.1f} MB")
    print(f"Completed in {elapsed:.0f}s")
    print("=" * 60)

if __name__ == "__main__":
    main()
