"""
Feature extractor using ResNet50.

When a fine-tuned CardEmbedder (card_classifier.pt) is available, uses that
for 512-D embeddings trained with triplet loss.  Otherwise falls back to
the vanilla ResNet50 backbone producing 2048-D features.

IMPORTANT: the card_index.npz must match the model in use.  After switching
models, rebuild the index with `python train_classifier.py --rebuild-index`.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import io
from pathlib import Path

INPUT_SIZE = 224

TRANSFORM = transforms.Compose([
    transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

_CLASSIFIER_PATH = Path(__file__).parent / "models" / "card_classifier.pt"


# ---------------------------------------------------------------------------
# CardEmbedder (same architecture as train_classifier.py)
# ---------------------------------------------------------------------------

class CardEmbedder(nn.Module):
    """ResNet50 backbone + projection head for metric learning."""

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


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

_MODEL: nn.Module | None = None
_USING_FINETUNED = False


def _load_model() -> nn.Module:
    global _USING_FINETUNED

    if _CLASSIFIER_PATH.exists():
        try:
            model = CardEmbedder(embed_dim=512)
            state = torch.load(str(_CLASSIFIER_PATH), map_location="cpu",
                               weights_only=True)
            model.load_state_dict(state)
            model.eval()
            _USING_FINETUNED = True
            print(f"[model] Loaded fine-tuned CardEmbedder (512-D) from {_CLASSIFIER_PATH}")
            return model
        except Exception as exc:
            print(f"[model] Failed to load fine-tuned model: {exc} — falling back to vanilla ResNet50")

    # Fallback: vanilla ResNet50 (2048-D)
    weights = models.ResNet50_Weights.DEFAULT
    backbone = models.resnet50(weights=weights)
    model = nn.Sequential(*list(backbone.children())[:-1])
    model.eval()
    _USING_FINETUNED = False
    print("[model] Using vanilla ResNet50 (2048-D)")
    return model


def get_model() -> nn.Module:
    """Return a cached instance of the feature extractor."""
    global _MODEL
    if _MODEL is None:
        _MODEL = _load_model()
    return _MODEL


def is_finetuned() -> bool:
    """Check if we're using the fine-tuned model."""
    return _USING_FINETUNED


def prewarm() -> None:
    """Pre-warm the model so the first real scan isn't slow."""
    model = get_model()
    dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE)
    with torch.inference_mode():
        model(dummy)
    tag = "CardEmbedder 512-D" if _USING_FINETUNED else "ResNet50 2048-D"
    print(f"[model] {tag} pre-warmed.")


def extract_features(image_bytes: bytes) -> np.ndarray:
    """
    Extract a normalised feature vector from raw image bytes.
    Returns 512-D if fine-tuned model is loaded, 2048-D otherwise.
    """
    model = get_model()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = TRANSFORM(img).unsqueeze(0)
    with torch.inference_mode():
        features = model(tensor)
    features = features.squeeze().numpy()
    # Fine-tuned model already L2-normalises; vanilla needs it
    if not _USING_FINETUNED:
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm
    return features.astype(np.float32)


def extract_features_from_url(url: str) -> np.ndarray | None:
    """Download an image from a URL and extract its features."""
    import requests
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return extract_features(resp.content)
    except Exception:
        return None
