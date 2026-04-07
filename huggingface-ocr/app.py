"""
Poketeer Card OCR API — Hugging Face Spaces

Receives a Pokemon card image, runs PaddleOCR to extract all text,
and returns structured results with bounding box positions so the
client can identify:
  - Card name (top region)
  - Card number + set code (bottom region)

Supports EN, JA, TH text natively.
"""

import io
import os
import re

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from paddleocr import PaddleOCR

# ---------------------------------------------------------------------------
# Initialize PaddleOCR — one instance per language for best accuracy
# ---------------------------------------------------------------------------

# Use multilingual model that handles EN + JA + TH
# 'en' model is fastest and handles Latin text
# 'japan' model handles Japanese + English
# 'latin' model is a good general-purpose option
# We'll use 'multilingual' approach: detect with 'en' first, then 'japan' if needed

ocr_en = PaddleOCR(
    use_angle_cls=True,
    lang="en",
    use_gpu=False,
    show_log=False,
    det_db_thresh=0.3,
    rec_batch_num=8,
)

ocr_ja = PaddleOCR(
    use_angle_cls=True,
    lang="japan",
    use_gpu=False,
    show_log=False,
    det_db_thresh=0.3,
    rec_batch_num=8,
)

print("[poketeer-ocr] PaddleOCR loaded (EN + JA)")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_relative_position(bbox, img_w, img_h):
    """Convert bounding box to relative position (0-1) within the image."""
    # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    ys = [p[1] for p in bbox]
    xs = [p[0] for p in bbox]
    return {
        "y_center": (min(ys) + max(ys)) / 2 / img_h,
        "x_center": (min(xs) + max(xs)) / 2 / img_w,
        "y_min": min(ys) / img_h,
        "y_max": max(ys) / img_h,
        "x_min": min(xs) / img_w,
        "x_max": max(xs) / img_w,
    }


def classify_region(pos):
    """Classify a text region as 'name', 'number', 'hp', or 'other'."""
    y = pos["y_center"]
    if y < 0.12:
        return "name"      # Top ~12% — card name
    elif y > 0.88:
        return "number"    # Bottom ~12% — card number / set code
    elif y < 0.18 and pos["x_max"] > 0.7:
        return "hp"        # Top-right — HP value
    return "other"


def extract_card_info(ocr_results, img_w, img_h):
    """
    Process PaddleOCR results and extract card-relevant fields.
    Returns structured card info.
    """
    texts = []

    if not ocr_results or not ocr_results[0]:
        return {"name": "", "number": "", "set_code": "", "all_text": [], "raw": []}

    for line in ocr_results[0]:
        bbox = line[0]
        text = line[1][0]
        confidence = line[1][1]
        pos = get_relative_position(bbox, img_w, img_h)
        region = classify_region(pos)

        texts.append({
            "text": text,
            "confidence": round(confidence, 3),
            "region": region,
            "position": {
                "y_center": round(pos["y_center"], 3),
                "x_center": round(pos["x_center"], 3),
            },
        })

    # Extract card name — highest confidence text in the name region
    name_texts = [t for t in texts if t["region"] == "name"]
    name_texts.sort(key=lambda t: t["confidence"], reverse=True)
    card_name = name_texts[0]["text"] if name_texts else ""

    # Extract card number — look for patterns like "123/456", "025", etc.
    number_texts = [t for t in texts if t["region"] == "number"]
    card_number = ""
    set_code = ""

    for t in number_texts:
        txt = t["text"]
        # Pattern: "025/172" or "25/172"
        num_match = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", txt)
        if num_match:
            card_number = num_match.group(1).lstrip("0") or "0"
            continue

        # Pattern: set code like "SV6", "S12a", "sv6pt5"
        set_match = re.search(r"\b([A-Za-z]{1,4}\d{1,3}[a-z]{0,3})\b", txt)
        if set_match and not set_code:
            set_code = set_match.group(1)

        # Bare number
        if not card_number:
            bare = re.search(r"\b(\d{1,4})\b", txt)
            if bare:
                card_number = bare.group(1).lstrip("0") or "0"

    return {
        "name": card_name,
        "number": card_number,
        "set_code": set_code,
        "all_text": texts,
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(title="Poketeer Card OCR")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "engine": "PaddleOCR", "languages": ["en", "ja", "th"]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr_card(file: UploadFile = File(...), lang: str = "en"):
    """
    Receive a card image, run PaddleOCR, return structured card info.

    Query params:
      - lang: "en" | "ja" | "th" (default "en")

    Returns:
      - name: detected card name
      - number: detected card number
      - set_code: detected set code
      - all_text: all detected text with positions and regions
    """
    contents = await file.read()
    img = Image.open(io.BytesIO(contents)).convert("RGB")
    img_w, img_h = img.size

    # Convert to numpy for PaddleOCR
    import numpy as np
    img_array = np.array(img)

    # Choose OCR engine based on language
    engine = ocr_ja if lang in ("ja", "th") else ocr_en

    # Run OCR
    result = engine.ocr(img_array, cls=True)

    # If Japanese OCR found very little, try English too and merge
    if lang in ("ja", "th") and result and result[0] and len(result[0]) < 3:
        result_en = ocr_en.ocr(img_array, cls=True)
        if result_en and result_en[0]:
            result[0].extend(result_en[0])

    # Extract structured card info
    card_info = extract_card_info(result, img_w, img_h)

    return card_info
