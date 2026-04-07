"""
Poketeer Card OCR API — Hugging Face Spaces

Receives a Pokemon card image, runs PaddleOCR to extract all text,
and returns structured results with bounding box positions so the
client can identify:
  - Card name (top region)
  - Card number + set code (bottom region)

Supports EN, JA, TH with auto-detection.
"""

import io
import re
import unicodedata

import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from paddleocr import PaddleOCR

# ---------------------------------------------------------------------------
# Initialize PaddleOCR — one instance per language
# ---------------------------------------------------------------------------

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

ocr_th = PaddleOCR(
    use_angle_cls=True,
    lang="th",
    use_gpu=False,
    show_log=False,
    det_db_thresh=0.3,
    rec_batch_num=8,
)

print("[poketeer-ocr] PaddleOCR loaded (EN + JA + TH)")

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

# Unicode ranges for script detection
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_JA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF]")


def detect_language(texts: list[str]) -> str:
    """
    Detect card language from OCR text.
    Returns 'th', 'ja', or 'en'.
    """
    combined = " ".join(texts)

    thai_count = len(_THAI_RE.findall(combined))
    ja_count = len(_JA_RE.findall(combined))

    if thai_count >= 3:
        return "th"
    if ja_count >= 2:
        return "ja"
    return "en"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_relative_position(bbox, img_w, img_h):
    """Convert bounding box to relative position (0-1) within the image."""
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
        return "name"
    elif y > 0.88:
        return "number"
    elif y < 0.18 and pos["x_max"] > 0.7:
        return "hp"
    return "other"


def extract_card_info(ocr_results, img_w, img_h):
    """
    Process PaddleOCR results and extract card-relevant fields.
    """
    texts = []

    if not ocr_results or not ocr_results[0]:
        return {"name": "", "number": "", "set_code": "", "all_text": []}

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

    # Extract card number
    number_texts = [t for t in texts if t["region"] == "number"]
    card_number = ""
    set_code = ""

    for t in number_texts:
        txt = t["text"]
        num_match = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", txt)
        if num_match:
            card_number = num_match.group(1).lstrip("0") or "0"
            continue

        set_match = re.search(r"\b([A-Za-z]{1,4}\d{1,3}[a-z]{0,3})\b", txt)
        if set_match and not set_code:
            set_code = set_match.group(1)

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
    return {"status": "ok", "engine": "PaddleOCR", "languages": ["en", "ja", "th", "auto"]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr_card(file: UploadFile = File(...), lang: str = "auto"):
    """
    Receive a card image, run PaddleOCR, return structured card info.

    Query params:
      - lang: "auto" | "en" | "ja" | "th" (default "auto")

    Returns:
      - name: detected card name
      - number: detected card number
      - set_code: detected set code
      - detected_lang: the language that was detected/used
      - all_text: all detected text with positions and regions
    """
    contents = await file.read()
    img = Image.open(io.BytesIO(contents)).convert("RGB")
    img_w, img_h = img.size
    img_array = np.array(img)

    if lang == "auto":
        # Step 1: Run EN engine (fastest) to get raw text for detection
        result_en = ocr_en.ocr(img_array, cls=True)
        en_texts = []
        if result_en and result_en[0]:
            en_texts = [line[1][0] for line in result_en[0]]

        detected = detect_language(en_texts)

        # Step 2: If non-English detected, re-run with the right engine
        if detected == "ja":
            result = ocr_ja.ocr(img_array, cls=True)
            # Merge EN results for number/set code region (Latin chars)
            if result and result[0] and result_en and result_en[0]:
                result[0].extend(result_en[0])
        elif detected == "th":
            result = ocr_th.ocr(img_array, cls=True)
            if result and result[0] and result_en and result_en[0]:
                result[0].extend(result_en[0])
        else:
            detected = "en"
            result = result_en
    else:
        detected = lang
        engines = {"ja": ocr_ja, "th": ocr_th}
        engine = engines.get(lang, ocr_en)
        result = engine.ocr(img_array, cls=True)

        # Merge EN results for non-English cards
        if lang in ("ja", "th") and result and result[0]:
            result_en = ocr_en.ocr(img_array, cls=True)
            if result_en and result_en[0]:
                result[0].extend(result_en[0])

    card_info = extract_card_info(result, img_w, img_h)
    card_info["detected_lang"] = detected

    return card_info
