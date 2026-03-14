"""
Export MobileNetV3-Small to ONNX for fast on-device inference.

This replaces the heavy ResNet50 (~26 MB) with a lightweight model (~4 MB)
that runs 10-20x faster on mobile WASM.

Produces:
  public/card_model.onnx         — MobileNetV3-Small ONNX (~4 MB)
  public/card_index_mobile.bin   — quantized feature index (576-D)
  public/card_index_meta.json    — card metadata

Usage:
    python -m backend.training.export_mobile_onnx   (from project root)
    python export_mobile_onnx.py                    (from backend/training/)
"""

import json
import struct
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

import numpy as np
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image


# ---------------------------------------------------------------------------
# MobileNetV3-Small feature extractor (576-D output)
# ---------------------------------------------------------------------------

class MobileFeatureExtractor(nn.Module):
    """MobileNetV3-Small as a feature extractor.

    Outputs L2-normalised 576-D embeddings.
    """
    def __init__(self):
        super().__init__()
        weights = models.MobileNet_V3_Small_Weights.DEFAULT
        backbone = models.mobilenet_v3_small(weights=weights)
        # Everything up to (and including) the adaptive avg pool
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        self.flatten = nn.Flatten()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.avgpool(x)
        x = self.flatten(x)
        # L2 normalise
        return torch.nn.functional.normalize(x, p=2, dim=1)


def export_model():
    output_dir = PROJECT_ROOT / "public"
    output_dir.mkdir(exist_ok=True)

    print("Building MobileNetV3-Small feature extractor...")
    model = MobileFeatureExtractor()
    model.eval()

    # Verify output dim
    with torch.no_grad():
        dummy = torch.randn(1, 3, 224, 224)
        out = model(dummy)
        feat_dim = out.shape[1]
        print(f"  Output dimension: {feat_dim}")

    # Export to ONNX
    print("Exporting to ONNX...")
    onnx_path = output_dir / "card_model.onnx"
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["image"],
        output_names=["features"],
        dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}},
        opset_version=17,
    )
    size_mb = onnx_path.stat().st_size / 1e6
    print(f"  Model: {onnx_path} ({size_mb:.1f} MB)")

    return feat_dim


def embed_all_cards(feat_dim: int):
    """Re-embed all cards using MobileNetV3-Small features."""
    import hashlib
    import io
    import requests

    index_path = BACKEND_DIR / "card_index.npz"
    output_dir = PROJECT_ROOT / "public"
    cache_dir = BACKEND_DIR / "_image_cache"
    cache_dir.mkdir(exist_ok=True)

    # Load existing index to get metadata (we'll reuse it)
    if not index_path.exists():
        print(f"ERROR: {index_path} not found.")
        return

    data = np.load(str(index_path), allow_pickle=False)
    metadata = json.loads(data["metadata"].tobytes().decode("utf-8"))
    n_cards = len(metadata)
    print(f"\nRe-embedding {n_cards} cards with MobileNetV3-Small...")
    print(f"  Image cache: {cache_dir}")

    # Build model
    model = MobileFeatureExtractor()
    model.eval()

    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    def load_image(url: str) -> Image.Image | None:
        """Load image from local cache first, download if not cached."""
        if not url:
            return None
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_path = cache_dir / f"{url_hash}.jpg"
        if cache_path.exists():
            try:
                return Image.open(cache_path).convert("RGB")
            except Exception:
                cache_path.unlink(missing_ok=True)
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception:
            return None

    features = np.zeros((n_cards, feat_dim), dtype=np.float32)
    batch_size = 32
    failed = 0

    for batch_start in range(0, n_cards, batch_size):
        batch_end = min(batch_start + batch_size, n_cards)
        batch_cards = metadata[batch_start:batch_end]
        tensors = []

        for card in batch_cards:
            img = load_image(card.get("image_small", ""))
            if img is not None:
                tensors.append(transform(img))
            else:
                tensors.append(torch.zeros(3, 224, 224))
                failed += 1

        batch_tensor = torch.stack(tensors)
        with torch.no_grad():
            embeddings = model(batch_tensor).numpy()
        features[batch_start:batch_end] = embeddings

        done = batch_end
        if done % 500 == 0 or done == n_cards:
            print(f"  {done}/{n_cards} cards embedded ({failed} failed)")

    # Save as mobile binary index
    mins = features.min(axis=0).astype(np.float32)
    maxs = features.max(axis=0).astype(np.float32)
    ranges = maxs - mins
    ranges[ranges == 0] = 1.0
    quantized = ((features - mins) / ranges * 255).clip(0, 255).astype(np.uint8)

    bin_path = output_dir / "card_index_mobile.bin"
    with open(bin_path, "wb") as f:
        f.write(struct.pack("<II", n_cards, feat_dim))
        f.write(mins.tobytes())
        f.write(maxs.tobytes())
        f.write(quantized.tobytes())
    print(f"  Index: {bin_path} ({bin_path.stat().st_size / 1e6:.1f} MB)")

    # Write metadata JSON
    meta_path = output_dir / "card_index_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)
    print(f"  Meta: {meta_path} ({meta_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    feat_dim = export_model()
    if feat_dim:
        embed_all_cards(feat_dim)
    print("\nDone! Rebuild APK to include the lightweight model.")
