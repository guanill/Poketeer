"""
card_detector.py — Pokémon card detection using Roboflow models.

This module provides two detection backends:
  1. Roboflow Hosted API  — uses inference-sdk to call a hosted model on Roboflow
  2. Local YOLO model     — downloads and runs a YOLO model locally via ultralytics

The detector finds card boundaries in photos so the identification pipeline
can work on a clean crop instead of a messy background.

Environment variables:
  ROBOFLOW_API_KEY     — required for hosted inference; get one free at roboflow.com
  ROBOFLOW_MODEL_ID    — model endpoint (default: pokemon-card-detector-cuyon/1)
  CARD_DETECTOR_MODE   — "roboflow" | "local" | "off" (default: "roboflow")
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
import numpy as np
from PIL import Image

# Load .env from the backend directory
load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
ROBOFLOW_MODEL_ID = os.getenv("ROBOFLOW_MODEL_ID", "pokemon-card-detector-cuyon/1")
DETECTOR_MODE = os.getenv("CARD_DETECTOR_MODE", "roboflow")  # "roboflow" | "local" | "off"

# Minimum confidence to accept a detection
MIN_CONFIDENCE = 0.4

# Padding around detected card (fraction of card size)
PAD_FRACTION = 0.03

# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------

class Detection:
    """A detected card bounding box."""
    __slots__ = ("x1", "y1", "x2", "y2", "confidence", "class_name")

    def __init__(self, x1: int, y1: int, x2: int, y2: int,
                 confidence: float, class_name: str = "card"):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.confidence = confidence
        self.class_name = class_name

    def area(self) -> int:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    def __repr__(self) -> str:
        return (f"Detection(({self.x1},{self.y1})-({self.x2},{self.y2}) "
                f"conf={self.confidence:.2f} cls={self.class_name})")


# ---------------------------------------------------------------------------
# Roboflow hosted inference
# ---------------------------------------------------------------------------

_RF_CLIENT = None


def _get_roboflow_client():
    """Lazily initialise the Roboflow inference client."""
    global _RF_CLIENT
    if _RF_CLIENT is not None:
        return _RF_CLIENT

    if not ROBOFLOW_API_KEY:
        print("[detector] ROBOFLOW_API_KEY not set — hosted detection disabled")
        return None

    try:
        from inference_sdk import InferenceHTTPClient
        _RF_CLIENT = InferenceHTTPClient(
            api_url="https://detect.roboflow.com",
            api_key=ROBOFLOW_API_KEY,
        )
        print(f"[detector] Roboflow client initialised (model: {ROBOFLOW_MODEL_ID})")
        return _RF_CLIENT
    except ImportError:
        print("[detector] inference-sdk not installed — run: pip install inference-sdk")
        return None


def detect_roboflow(image_bytes: bytes) -> list[Detection]:
    """Detect cards using Roboflow's hosted inference API."""
    client = _get_roboflow_client()
    if client is None:
        return []

    try:
        import tempfile
        # inference-sdk expects a file path or URL
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        result = client.infer(tmp_path, model_id=ROBOFLOW_MODEL_ID)
        os.unlink(tmp_path)

        detections = []
        for pred in result.get("predictions", []):
            cx = pred["x"]
            cy = pred["y"]
            w = pred["width"]
            h = pred["height"]
            conf = pred["confidence"]
            cls = pred.get("class", "card")

            if conf < MIN_CONFIDENCE:
                continue

            x1 = int(cx - w / 2)
            y1 = int(cy - h / 2)
            x2 = int(cx + w / 2)
            y2 = int(cy + h / 2)
            detections.append(Detection(x1, y1, x2, y2, conf, cls))

        detections.sort(key=lambda d: -d.confidence)
        return detections

    except Exception as exc:
        print(f"[detector] Roboflow inference failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Local YOLO inference (ultralytics)
# ---------------------------------------------------------------------------

_LOCAL_MODEL = None
_LOCAL_MODEL_PATH = Path(__file__).parent / "models" / "card_detector.pt"


def _get_local_model():
    """Load a locally saved YOLO model."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is not None:
        return _LOCAL_MODEL

    if not _LOCAL_MODEL_PATH.exists():
        print(f"[detector] Local model not found at {_LOCAL_MODEL_PATH}")
        return None

    try:
        from ultralytics import YOLO
        _LOCAL_MODEL = YOLO(str(_LOCAL_MODEL_PATH))
        print(f"[detector] Local YOLO model loaded from {_LOCAL_MODEL_PATH}")
        return _LOCAL_MODEL
    except ImportError:
        print("[detector] ultralytics not installed — run: pip install ultralytics")
        return None


def detect_local(image_bytes: bytes) -> list[Detection]:
    """Detect cards using a local YOLO model."""
    model = _get_local_model()
    if model is None:
        return []

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = model(img, conf=MIN_CONFIDENCE, verbose=False)

        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, "card")
                detections.append(Detection(x1, y1, x2, y2, conf, cls_name))

        detections.sort(key=lambda d: -d.confidence)
        return detections

    except Exception as exc:
        print(f"[detector] Local YOLO inference failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Unified detection API
# ---------------------------------------------------------------------------

def detect_cards(image_bytes: bytes) -> list[Detection]:
    """
    Detect Pokémon cards in the image using the configured backend.
    Returns a list of Detection objects sorted by confidence (highest first).
    """
    if DETECTOR_MODE == "off":
        return []

    if DETECTOR_MODE == "local":
        return detect_local(image_bytes)

    # Default: Roboflow hosted, fall back to local
    detections = detect_roboflow(image_bytes)
    if not detections:
        detections = detect_local(image_bytes)
    return detections


def crop_best_card(image_bytes: bytes) -> bytes:
    """
    Detect cards and return the best card crop as JPEG bytes.
    If no card is detected, returns the original image.

    Applies padding around the detection for cleaner crops.
    """
    detections = detect_cards(image_bytes)
    if not detections:
        return image_bytes

    best = detections[0]
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size

    # Add padding
    pad_x = int((best.x2 - best.x1) * PAD_FRACTION)
    pad_y = int((best.y2 - best.y1) * PAD_FRACTION)

    x1 = max(0, best.x1 - pad_x)
    y1 = max(0, best.y1 - pad_y)
    x2 = min(w, best.x2 + pad_x)
    y2 = min(h, best.y2 + pad_y)

    cropped = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def is_available() -> bool:
    """Check if any detection backend is configured and available."""
    if DETECTOR_MODE == "off":
        return False
    if DETECTOR_MODE == "roboflow":
        return bool(ROBOFLOW_API_KEY)
    if DETECTOR_MODE == "local":
        return _LOCAL_MODEL_PATH.exists()
    return False
