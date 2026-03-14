"""
Poketeer Card Embedder API — Hugging Face Spaces

Receives a Pokemon card image, returns a 512-D embedding vector.
The client sends this embedding to Supabase pgvector for matching.
"""

import io
import json

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as transforms
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# ---------------------------------------------------------------------------
# Model (same architecture as backend/model.py)
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

# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

INPUT_SIZE = 224

transform = transforms.Compose([
    transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

# ---------------------------------------------------------------------------
# Load model
# ---------------------------------------------------------------------------

model = CardEmbedder(embed_dim=512)
state = torch.load("card_classifier.pt", map_location="cpu", weights_only=True)
model.load_state_dict(state)
model.eval()
print("[poketeer] CardEmbedder loaded (512-D)")

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(title="Poketeer Card Embedder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "model": "CardEmbedder", "dim": 512}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/embed")
async def embed(file: UploadFile = File(...)):
    """Receive a card image, return 512-D embedding."""
    contents = await file.read()
    img = Image.open(io.BytesIO(contents)).convert("RGB")
    tensor = transform(img).unsqueeze(0)

    with torch.inference_mode():
        features = model(tensor)

    embedding = features.squeeze().numpy().tolist()
    return {"embedding": embedding, "dim": len(embedding)}
