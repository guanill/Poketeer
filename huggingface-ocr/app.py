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

_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_JA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF]")
# Latin suffixes that appear on JA/TH cards — don't count as "English"
_JA_SUFFIXES = re.compile(r"\b(ex|EX|GX|V|VSTAR|VMAX|VUNION|BREAK|TAG\s*TEAM|Lv\.\s*X|M\s)\b")


def detect_language(all_lines: list[dict]) -> str:
    """
    Detect card language from OCR results.
    Focuses on the NAME region for script detection since
    number/set regions are always Latin.
    Returns 'th', 'ja', or 'en'.
    """
    # Prioritize name region text for detection
    name_texts = [t["text"] for t in all_lines if t.get("region") == "name"]
    other_texts = [t["text"] for t in all_lines if t.get("region") == "other"]
    # Check name region first, then all non-number text
    for texts in [name_texts, other_texts, [t["text"] for t in all_lines]]:
        combined = " ".join(texts)
        # Strip out known Latin suffixes that appear on JA/TH cards
        cleaned = _JA_SUFFIXES.sub("", combined)

        thai_count = len(_THAI_RE.findall(cleaned))
        ja_count = len(_JA_RE.findall(cleaned))

        if thai_count >= 2:
            return "th"
        if ja_count >= 1:
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
    """
    Classify a text region as 'name', 'number', 'hp', or 'other'.
    Wider regions than before to handle slightly off-center photos.
    """
    y = pos["y_center"]
    if y < 0.15:
        return "name"      # Top ~15% — card name
    elif y > 0.85:
        return "number"    # Bottom ~15% — card number / set code
    elif y < 0.20 and pos["x_max"] > 0.65:
        return "hp"        # Top-right — HP value
    return "other"


def deduplicate_results(lines: list) -> list:
    """
    Remove duplicate detections from merged EN+JA/TH results.
    Two detections are duplicates if their centers are very close.
    Keep the one with higher confidence.
    """
    if not lines:
        return lines

    kept = []
    for line in lines:
        bbox = line[0]
        text = line[1][0]
        conf = line[1][1]
        cy = sum(p[1] for p in bbox) / 4
        cx = sum(p[0] for p in bbox) / 4

        is_dup = False
        for i, (kb, kt, kc, kcx, kcy) in enumerate(kept):
            # If centers are within 2% of image, consider duplicate
            if abs(cx - kcx) < 20 and abs(cy - kcy) < 20:
                is_dup = True
                # Keep higher confidence
                if conf > kc:
                    kept[i] = (bbox, (text, conf), conf, cx, cy)
                break

        if not is_dup:
            kept.append((bbox, (text, conf), conf, cx, cy))

    return [[k[0], k[1]] for k in kept]


# Set code patterns — comprehensive list
_SET_CODE_PATTERNS = [
    # SV era: SV1, SV6pt5, SV11s, SV4a, SV2P, etc.
    r"(SV\d{1,2}[a-z]{0,4})",
    # S era: S1W, S12a, S5I, S10P, etc.
    r"(S\d{1,2}[a-zA-Z]{0,2})",
    # SM era: SM1S, SM12a, SM5+, etc.
    r"(SM\d{1,2}[a-zA-Z+]{0,2})",
    # XY era: XY1, XY12a, etc.
    r"(XY\d{1,2}[a-z]{0,2})",
    # BW era: BW1, BW11, etc.
    r"(BW\d{1,2}[a-z]{0,2})",
    # SWSH promos: SWSH, etc.
    r"(SWSH\d{0,3})",
    # Special sets: MEW, SVP, etc.
    r"(MEW|SVP|SMP\d?)",
    # Thai sets: SC1a, SC3b, MA1, MA2, MA3, MA4
    r"(SC\d[a-z]?|MA\d)",
    # Classic sets: PCG, ADV, etc.
    r"(PCG\d{1,2}|ADV\d{1,2}|CP\d{1,2}|L\d[a-z]?)",
    # General fallback: 1-4 letters + 1-3 digits + optional suffix
    r"([A-Za-z]{1,4}\d{1,3}[a-z]{0,3})",
]


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

    # ── Extract card name ──
    # Primary: highest confidence text in name region
    name_texts = [t for t in texts if t["region"] == "name"]
    name_texts.sort(key=lambda t: t["confidence"], reverse=True)
    card_name = ""

    if name_texts:
        # Filter out junk (HP values, stage labels)
        for nt in name_texts:
            txt = nt["text"].strip()
            if re.match(r"^\d+$", txt):  # Pure number = HP, skip
                continue
            if re.match(r"^(HP|hp)\s*\d+", txt):  # "HP 120"
                continue
            if re.match(r"^(Stage|Basic|BASIC|STAGE)\b", txt, re.I):
                continue
            card_name = txt
            break

    # Fallback: if no name found in name region, try top 25% of card
    if not card_name:
        top_quarter = [t for t in texts if t["position"]["y_center"] < 0.25]
        top_quarter.sort(key=lambda t: t["confidence"], reverse=True)
        for t in top_quarter:
            txt = t["text"].strip()
            if len(txt) >= 2 and not re.match(r"^\d+$", txt):
                card_name = txt
                break

    # ── Extract card number and set code ──
    number_texts = [t for t in texts if t["region"] == "number"]
    # Also check bottom 20% as fallback
    if not number_texts:
        number_texts = [t for t in texts if t["position"]["y_center"] > 0.80]

    card_number = ""
    set_code = ""

    # Collect all bottom text for combined analysis
    bottom_combined = " ".join(t["text"] for t in number_texts)

    # Pattern: "025/172" or "25/172" — with OCR misread corrections
    corrected = bottom_combined.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    num_match = re.search(r"(\d{1,4})\s*[/\\|]\s*(\d{1,4})", corrected)
    if num_match:
        card_number = num_match.group(1).lstrip("0") or "0"

    # Try each text block individually if combined didn't work
    if not card_number:
        for t in number_texts:
            txt = t["text"]
            corrected_txt = txt.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
            m = re.search(r"(\d{1,4})\s*[/\\|]\s*(\d{1,4})", corrected_txt)
            if m:
                card_number = m.group(1).lstrip("0") or "0"
                break

    # Bare number fallback
    if not card_number:
        for t in number_texts:
            txt = t["text"]
            bare = re.search(r"\b(\d{1,4})\b", txt)
            if bare:
                card_number = bare.group(1).lstrip("0") or "0"
                break

    # Set code extraction — try all patterns on combined bottom text
    for pattern in _SET_CODE_PATTERNS:
        m = re.search(pattern, bottom_combined, re.I)
        if m:
            set_code = m.group(1)
            break

    # Also try individual bottom text blocks
    if not set_code:
        for t in number_texts:
            for pattern in _SET_CODE_PATTERNS:
                m = re.search(pattern, t["text"], re.I)
                if m:
                    set_code = m.group(1)
                    break
            if set_code:
                break

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
        # Step 1: Run EN engine (fastest) to get raw text + positions
        result_en = ocr_en.ocr(img_array, cls=True)

        # Build position-aware text list for language detection
        en_annotated = []
        if result_en and result_en[0]:
            for line in result_en[0]:
                pos = get_relative_position(line[0], img_w, img_h)
                region = classify_region(pos)
                en_annotated.append({"text": line[1][0], "region": region})

        detected = detect_language(en_annotated)

        # Step 2: If non-English detected, re-run with the right engine
        if detected == "ja":
            result_native = ocr_ja.ocr(img_array, cls=True)
        elif detected == "th":
            result_native = ocr_th.ocr(img_array, cls=True)
        else:
            detected = "en"
            result_native = None

        if result_native and result_native[0]:
            # Merge: native engine results + EN engine results, deduplicated
            merged = list(result_native[0])
            if result_en and result_en[0]:
                merged.extend(result_en[0])
            result = [deduplicate_results(merged)]
        else:
            result = result_en
    else:
        detected = lang
        engines = {"ja": ocr_ja, "th": ocr_th}
        engine = engines.get(lang, ocr_en)
        result = engine.ocr(img_array, cls=True)

        # Merge EN results for non-English cards (helps with Latin number/set regions)
        if lang in ("ja", "th") and result and result[0]:
            result_en = ocr_en.ocr(img_array, cls=True)
            if result_en and result_en[0]:
                merged = list(result[0]) + list(result_en[0])
                result = [deduplicate_results(merged)]

    card_info = extract_card_info(result, img_w, img_h)
    card_info["detected_lang"] = detected

    return card_info
