"""
Export the fine-tuned CardEmbedder to ONNX format for on-device inference.

Produces:
  public/card_model.onnx         — quantized ONNX model (~25 MB)
  public/card_index_mobile.bin   — quantized 512-D feature index
  public/card_index_meta.json    — card metadata for the index

Usage:
    python -m backend.training.export_onnx   (from project root)
    python export_onnx.py                    (from backend/training/)
"""

import json
import struct
from pathlib import Path

# Resolve paths relative to backend/ regardless of where the script lives
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models


# ---------------------------------------------------------------------------
# CardEmbedder (must match train_classifier.py)
# ---------------------------------------------------------------------------

class CardEmbedder(nn.Module):
    def __init__(self, embed_dim: int = 512, freeze_backbone_layers: int = 6):
        super().__init__()
        weights = models.ResNet50_Weights.DEFAULT
        backbone = models.resnet50(weights=weights)
        children = list(backbone.children())
        for i, child in enumerate(children[:freeze_backbone_layers]):
            for param in child.parameters():
                param.requires_grad = False
        self.backbone = nn.Sequential(*children[:-1])
        self.flatten = nn.Flatten()
        self.projector = nn.Sequential(
            nn.Linear(2048, 1024),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(1024, embed_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone(x)
        features = self.flatten(features)
        embeddings = self.projector(features)
        return F.normalize(embeddings, p=2, dim=1)


def export_model():
    model_path = BACKEND_DIR / "models" / "card_classifier.pt"
    output_dir = PROJECT_ROOT / "public"

    if not model_path.exists():
        print(f"ERROR: {model_path} not found. Train first.")
        return

    print("Loading fine-tuned model...")
    model = CardEmbedder(embed_dim=512)
    state = torch.load(str(model_path), map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()

    # Export to ONNX
    print("Exporting to ONNX...")
    dummy = torch.randn(1, 3, 224, 224)
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
    print(f"  Full model: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)")

    # Quantize with ONNX Runtime
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
        quantized_path = output_dir / "card_model_q.onnx"
        quantize_dynamic(
            str(onnx_path),
            str(quantized_path),
            weight_type=QuantType.QUInt8,
        )
        # Replace full with quantized
        quantized_path.replace(onnx_path)
        print(f"  Quantized: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)")
    except ImportError:
        print("  WARNING: onnxruntime not installed, skipping quantization")
        print("  Install with: pip install onnxruntime")


def export_index():
    """Convert card_index.npz to a quantized binary format for the frontend."""
    index_path = BACKEND_DIR / "card_index.npz"
    output_dir = PROJECT_ROOT / "public"
    embed_dim = 512

    if not index_path.exists():
        print(f"ERROR: {index_path} not found. Rebuild index first.")
        return

    print("Loading card index...")
    data = np.load(str(index_path), allow_pickle=False)
    features = data["features"]  # (N, 512) float32
    metadata = json.loads(data["metadata"].tobytes().decode("utf-8"))

    n_cards = features.shape[0]
    feat_dim = features.shape[1]
    print(f"  {n_cards} cards, {feat_dim}-D features")

    if feat_dim != embed_dim:
        print(f"  WARNING: Expected {embed_dim}-D but got {feat_dim}-D")
        embed_dim = feat_dim

    # Quantize features to uint8 per-dimension
    mins = features.min(axis=0).astype(np.float32)
    maxs = features.max(axis=0).astype(np.float32)

    # Avoid division by zero
    ranges = maxs - mins
    ranges[ranges == 0] = 1.0

    quantized = ((features - mins) / ranges * 255).clip(0, 255).astype(np.uint8)

    # Write binary: [n_cards:u32] [dim:u32] [mins:f32*dim] [maxs:f32*dim] [data:u8*n*dim]
    bin_path = output_dir / "card_index_mobile.bin"
    with open(bin_path, "wb") as f:
        f.write(struct.pack("<II", n_cards, embed_dim))
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
    export_model()
    export_index()
    print("\nDone! Rebuild APK to include updated model and index.")
