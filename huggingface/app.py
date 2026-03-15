"""
Poketeer Card Embedder API — Hugging Face Spaces

Receives a Pokemon card image, returns a 512-D embedding vector
using DINOv2 ViT-B/14 + learned projection.
The client sends this embedding to Supabase pgvector for matching.
"""

import io

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# ---------------------------------------------------------------------------
# DINOv2 backbone + projection
# ---------------------------------------------------------------------------

dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14")
dinov2.eval()

projection = nn.Linear(768, 512, bias=False)
proj_state = torch.load("dinov2_projection.pt", map_location="cpu", weights_only=True)
projection.load_state_dict(proj_state)
projection.eval()

print("[poketeer] DINOv2 ViT-B/14 + projection loaded (768→512-D)")

# ---------------------------------------------------------------------------
# Preprocessing (must match Colab training)
# ---------------------------------------------------------------------------

transform = transforms.Compose([
    transforms.Resize(252, interpolation=transforms.InterpolationMode.BICUBIC),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

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
    return {"status": "ok", "model": "DINOv2-ViT-B/14", "dim": 512}

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
        features = dinov2(tensor)           # (1, 768)
        emb = projection(features)          # (1, 512)
        emb = F.normalize(emb, p=2, dim=1)

    embedding = emb.squeeze().numpy().tolist()
    return {"embedding": embedding, "dim": len(embedding)}
