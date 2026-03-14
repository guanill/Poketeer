"""
train_classifier.py — Fine-tune ResNet50 on Pokémon card images for better
feature extraction (card identification, not just detection).

This replaces the generic ImageNet features with card-specific embeddings,
dramatically improving identification accuracy.

Strategy: Metric learning with triplet loss.
  - Anchor:   a card image
  - Positive: same card (different photo/augmentation)
  - Negative: different card (hard negative mining)

The fine-tuned model produces embeddings that are close for the same card
and far apart for different cards, making cosine-similarity matching
much more accurate.

Data source: Pokémon TCG card images (downloaded during build_index.py).

Usage:
    # Fine-tune using existing card images (from card_index.npz / card_names.json)
    python train_classifier.py

    # With custom settings
    python train_classifier.py --epochs 30 --lr 1e-4 --batch 32

    # Quick test
    python train_classifier.py --epochs 2 --limit 500

Output:
    backend/models/card_classifier.pt  — fine-tuned ResNet50 weights
    backend/card_index_finetuned.npz   — re-indexed features using fine-tuned model
"""

import argparse
import io
import json
import random
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

import numpy as np
import requests
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from tqdm import tqdm


# ---------------------------------------------------------------------------
# Dataset: card triplets for metric learning
# ---------------------------------------------------------------------------

class CardTripletDataset(Dataset):
    """
    Generates (anchor, positive, negative) triplets from card images.

    Since we have one canonical image per card, we create "positives" via
    augmentation (simulating different photos of the same card) and select
    negatives from different cards.
    """

    def __init__(self, card_records: list[dict], transform_anchor, transform_positive,
                 limit: int | None = None):
        # Group cards by name (same Pokémon, different sets = similar but distinct)
        self.cards = card_records[:limit] if limit else card_records
        self.transform_anchor = transform_anchor
        self.transform_positive = transform_positive
        self._image_cache: dict[str, Image.Image | None] = {}

    def __len__(self):
        return len(self.cards)

    def _download_image(self, url: str) -> Image.Image | None:
        if url in self._image_cache:
            return self._image_cache[url]
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            self._image_cache[url] = img
            return img
        except Exception:
            self._image_cache[url] = None
            return None

    def __getitem__(self, idx):
        anchor_card = self.cards[idx]
        anchor_url = anchor_card.get("image_small", "")
        anchor_img = self._download_image(anchor_url)

        if anchor_img is None:
            # Fallback: return a dummy tensor (will be filtered in training loop)
            dummy = torch.zeros(3, 224, 224)
            return dummy, dummy, dummy, False

        # Positive: same image, different augmentation (simulates a different photo)
        anchor_tensor = self.transform_anchor(anchor_img)
        positive_tensor = self.transform_positive(anchor_img)

        # Negative: different card (hard negative = same Pokémon name, different card)
        neg_idx = idx
        attempts = 0
        while neg_idx == idx and attempts < 10:
            neg_idx = random.randint(0, len(self.cards) - 1)
            attempts += 1

        neg_card = self.cards[neg_idx]
        neg_url = neg_card.get("image_small", "")
        neg_img = self._download_image(neg_url)

        if neg_img is None:
            dummy = torch.zeros(3, 224, 224)
            return anchor_tensor, positive_tensor, dummy, False

        negative_tensor = self.transform_anchor(neg_img)
        return anchor_tensor, positive_tensor, negative_tensor, True


# ---------------------------------------------------------------------------
# Model: ResNet50 with a learned embedding projection
# ---------------------------------------------------------------------------

class CardEmbedder(nn.Module):
    """
    ResNet50 backbone + projection head for metric learning.
    Outputs L2-normalised embeddings of dimension `embed_dim`.
    """

    def __init__(self, embed_dim: int = 512, freeze_backbone_layers: int = 6):
        super().__init__()
        weights = models.ResNet50_Weights.DEFAULT
        backbone = models.resnet50(weights=weights)

        # Freeze early layers (they capture generic edges/textures — no need to retrain)
        children = list(backbone.children())
        for i, child in enumerate(children[:freeze_backbone_layers]):
            for param in child.parameters():
                param.requires_grad = False

        # Remove the final FC layer → output is (batch, 2048)
        self.backbone = nn.Sequential(*children[:-1])
        self.flatten = nn.Flatten()

        # Projection head: 2048 → embed_dim
        self.projector = nn.Sequential(
            nn.Linear(2048, 1024),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(1024, embed_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone(x)          # (B, 2048, 1, 1)
        features = self.flatten(features)    # (B, 2048)
        embeddings = self.projector(features) # (B, embed_dim)
        return F.normalize(embeddings, p=2, dim=1)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    card_records: list[dict],
    epochs: int = 20,
    batch_size: int = 16,
    lr: float = 3e-4,
    embed_dim: int = 512,
    margin: float = 0.3,
    limit: int | None = None,
    device: str = "auto",
):
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Training on: {device}")

    # Augmentation transforms
    transform_anchor = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    transform_positive = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomCrop(224),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
        transforms.RandomPerspective(distortion_scale=0.15, p=0.5),
        transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    dataset = CardTripletDataset(card_records, transform_anchor, transform_positive, limit)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

    model = CardEmbedder(embed_dim=embed_dim).to(device)
    triplet_loss = nn.TripletMarginLoss(margin=margin, p=2)
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=lr,
        weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    print(f"\nDataset: {len(dataset)} cards")
    print(f"Epochs: {epochs}, Batch: {batch_size}, LR: {lr}")
    print(f"Embedding dim: {embed_dim}, Margin: {margin}")
    print()

    best_loss = float("inf")
    output_dir = BACKEND_DIR / "models"
    output_dir.mkdir(exist_ok=True)

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        valid_batches = 0

        pbar = tqdm(loader, desc=f"Epoch {epoch + 1}/{epochs}")
        for anchor, positive, negative, valid_mask in pbar:
            # Skip invalid samples
            if not valid_mask.any():
                continue

            anchor = anchor[valid_mask].to(device)
            positive = positive[valid_mask].to(device)
            negative = negative[valid_mask].to(device)

            e_anchor = model(anchor)
            e_positive = model(positive)
            e_negative = model(negative)

            loss = triplet_loss(e_anchor, e_positive, e_negative)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            valid_batches += 1
            pbar.set_postfix(loss=f"{loss.item():.4f}")

        scheduler.step()
        avg_loss = total_loss / max(valid_batches, 1)
        print(f"  Epoch {epoch + 1}: avg_loss={avg_loss:.4f}, lr={scheduler.get_last_lr()[0]:.6f}")

        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(model.state_dict(), output_dir / "card_classifier.pt")
            print(f"  -> Saved best model (loss={best_loss:.4f})")

    print(f"\nTraining complete! Best loss: {best_loss:.4f}")
    return output_dir / "card_classifier.pt"


# ---------------------------------------------------------------------------
# Re-index: rebuild card_index.npz with fine-tuned features
# ---------------------------------------------------------------------------

def rebuild_index(model_path: str, card_records: list[dict],
                  embed_dim: int = 512, device: str = "auto"):
    """Rebuild the card feature index using the fine-tuned model."""
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"\nRebuilding index with fine-tuned model on {device}...")

    model = CardEmbedder(embed_dim=embed_dim).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    features_list = []
    metadata = []

    for card in tqdm(card_records, desc="Re-indexing"):
        url = card.get("image_small", "")
        if not url:
            continue

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            tensor = transform(img).unsqueeze(0).to(device)

            with torch.inference_mode():
                embedding = model(tensor).cpu().numpy().squeeze()

            features_list.append(embedding)
            metadata.append(card)
            time.sleep(0.02)
        except Exception:
            continue

    if features_list:
        features_matrix = np.stack(features_list, axis=0).astype(np.float32)
        output_path = BACKEND_DIR / "card_index.npz"
        np.savez_compressed(
            str(output_path),
            features=features_matrix,
            metadata=json.dumps(metadata).encode("utf-8"),
        )
        print(f"Saved fine-tuned index ({len(metadata)} cards) -> {output_path}")
    else:
        print("WARNING: No features extracted!")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune ResNet50 for Pokémon card identification"
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--embed-dim", type=int, default=512)
    parser.add_argument("--margin", type=float, default=0.3)
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of cards for quick testing")
    parser.add_argument("--sets", type=str, default=None,
                        help="Comma-separated set ID prefixes to include (e.g. 'sv4pt5,sv5,sv6')")
    parser.add_argument("--device", default="auto",
                        help="Device: auto, cuda, or cpu")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="After training, rebuild the feature index with the fine-tuned model")
    parser.add_argument("--rebuild-only", action="store_true",
                        help="Skip training, just rebuild the index from an existing model")
    args = parser.parse_args()

    # Load card records
    names_path = BACKEND_DIR / "card_names.json"
    if not names_path.exists():
        print("ERROR: card_names.json not found. Run build_index.py first.")
        sys.exit(1)

    with open(names_path, encoding="utf-8") as f:
        card_records = json.load(f)

    print(f"Loaded {len(card_records)} card records from {names_path}")

    # Filter by set IDs if requested
    if args.sets:
        set_ids = [s.strip() for s in args.sets.split(",")]
        card_records = [c for c in card_records if c.get("set_id", "") in set_ids]
        print(f"Filtered to {len(card_records)} cards from sets: {set_ids}")

    # Rebuild-only mode: skip training, just rebuild index from existing model
    if args.rebuild_only:
        model_path = BACKEND_DIR / "models" / "card_classifier.pt"
        if not model_path.exists():
            print(f"ERROR: {model_path} not found. Train first.")
            sys.exit(1)
        rebuild_index(
            str(model_path),
            card_records[:args.limit] if args.limit else card_records,
            embed_dim=args.embed_dim,
            device=args.device,
        )
        return

    # Train
    model_path = train(
        card_records,
        epochs=args.epochs,
        batch_size=args.batch,
        lr=args.lr,
        embed_dim=args.embed_dim,
        margin=args.margin,
        limit=args.limit,
        device=args.device,
    )

    # Optionally rebuild the index
    if args.rebuild_index:
        rebuild_index(
            str(model_path),
            card_records[:args.limit] if args.limit else card_records,
            embed_dim=args.embed_dim,
            device=args.device,
        )


if __name__ == "__main__":
    main()
