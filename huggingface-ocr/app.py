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

import cv2
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

# Note: PaddleOCR has no Thai model. For TH cards we use the EN engine
# to read the card number and set code (always Latin text), which is
# sufficient to identify the card via DB lookup.
ocr_th = ocr_en  # Alias — Thai cards use EN engine

print("[poketeer-ocr] PaddleOCR loaded (EN + JA; TH uses EN engine)")

# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

# Standard Pokemon card aspect ratio is ~2.5 x 3.5 inches → ratio ~0.714
CARD_RATIO = 0.714
TARGET_W = 600
TARGET_H = int(TARGET_W / CARD_RATIO)


def order_points(pts):
    """Order 4 points as: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left has smallest sum
    rect[2] = pts[np.argmax(s)]   # bottom-right has largest sum
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]   # top-right has smallest difference
    rect[3] = pts[np.argmax(d)]   # bottom-left has largest difference
    return rect


def find_card_contour(img_bgr):
    """
    Try to find a card-shaped rectangle in the image.
    Returns 4 corner points or None if not found.
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Try multiple edge detection thresholds
    for low, high in [(30, 100), (50, 150), (20, 80)]:
        edges = cv2.Canny(blurred, low, high)
        # Dilate to close gaps in edges
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(cnt)
            # Card should be at least 10% of image area
            if area < (w * h * 0.10):
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                ordered = order_points(pts)

                # Check aspect ratio is roughly card-shaped (0.5–0.9)
                widthA = np.linalg.norm(ordered[1] - ordered[0])
                widthB = np.linalg.norm(ordered[2] - ordered[3])
                heightA = np.linalg.norm(ordered[3] - ordered[0])
                heightB = np.linalg.norm(ordered[2] - ordered[1])
                avg_w = (widthA + widthB) / 2
                avg_h = (heightA + heightB) / 2

                if avg_h < 1:
                    continue

                ratio = avg_w / avg_h
                # Accept cards in portrait (0.55-0.85) or landscape (1.2-1.8)
                if 0.55 <= ratio <= 0.85 or 1.2 <= ratio <= 1.8:
                    return ordered

    return None


def perspective_correct(img_bgr, corners):
    """Warp the card to a flat, upright rectangle."""
    ordered = order_points(corners)

    # Determine if landscape (wider than tall) and rotate
    widthA = np.linalg.norm(ordered[1] - ordered[0])
    heightA = np.linalg.norm(ordered[3] - ordered[0])
    is_landscape = widthA > heightA * 1.1

    if is_landscape:
        dst_w, dst_h = TARGET_H, TARGET_W
    else:
        dst_w, dst_h = TARGET_W, TARGET_H

    dst = np.array([
        [0, 0],
        [dst_w - 1, 0],
        [dst_w - 1, dst_h - 1],
        [0, dst_h - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(img_bgr, M, (dst_w, dst_h))

    # If landscape, rotate to portrait
    if is_landscape:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

    return warped


def enhance_for_ocr(img_bgr):
    """
    Enhance image for better OCR:
    - Auto white balance
    - Contrast normalization (CLAHE)
    - Sharpening
    """
    # Convert to LAB for better contrast handling
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # CLAHE on lightness channel — adaptive contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)

    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # Sharpen
    kernel = np.array([
        [0, -0.5, 0],
        [-0.5, 3, -0.5],
        [0, -0.5, 0],
    ])
    enhanced = cv2.filter2D(enhanced, -1, kernel)

    return enhanced


def preprocess_card(img_array: np.ndarray) -> np.ndarray:
    """
    Full preprocessing pipeline:
    1. Try to find and perspective-correct the card
    2. Enhance contrast and sharpness for OCR
    Returns the processed image as a numpy array (RGB).
    """
    # Convert RGB to BGR for OpenCV
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    # Step 1: Try perspective correction
    corners = find_card_contour(img_bgr)
    if corners is not None:
        img_bgr = perspective_correct(img_bgr, corners)

    # Step 2: Enhance for OCR
    img_bgr = enhance_for_ocr(img_bgr)

    # Convert back to RGB
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)


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
    # The card name is top-center. Stage labels ("Basic", "Stage 1", "たね",
    # "พื้นฐาน") sit in the top-LEFT (x < 0.30). HP is top-RIGHT (x > 0.70).
    # So we prioritize text in the center of the name region.
    _STAGE_RE = re.compile(
        r"^("
        r"Stage\s*[0-9]|Basic|BASIC|STAGE|Mega|MEGA|BREAK|Restored|RESTORED"
        r"|たね|たねポケモン|1進化|2進化|進化"                       # Japanese
        r"|พื้นฐาน|ร่าง\s*1|ร่าง\s*2|อื่น\s*ๆ"                  # Thai
        r"|V|VSTAR|VMAX|VUNION|V-UNION|TAG\s*TEAM"               # Suffixes alone
        r")\s*$", re.I
    )

    name_texts = [t for t in texts if t["region"] == "name"]

    # Sort: prefer center-x text (x_center 0.30–0.70) over far-left/right,
    # then by confidence
    def name_sort_key(t):
        xc = t["position"]["x_center"]
        is_center = 0.25 <= xc <= 0.75
        return (-int(is_center), -t["confidence"])

    name_texts.sort(key=name_sort_key)
    card_name = ""

    if name_texts:
        for nt in name_texts:
            txt = nt["text"].strip()
            xc = nt["position"]["x_center"]
            if re.match(r"^\d+$", txt):                    # Pure number (HP)
                continue
            if re.match(r"^(HP|hp)\s*\d+", txt):           # "HP 120"
                continue
            if _STAGE_RE.match(txt):                        # Stage label
                continue
            if xc < 0.20 and len(txt) <= 8:                # Far-left short text = likely stage
                continue
            card_name = txt
            break

    # Fallback: if no name found in name region, try top 25% of card
    if not card_name:
        top_quarter = [t for t in texts if t["position"]["y_center"] < 0.25]
        top_quarter.sort(key=name_sort_key)
        for t in top_quarter:
            txt = t["text"].strip()
            if len(txt) >= 2 and not re.match(r"^\d+$", txt) and not _STAGE_RE.match(txt):
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
    img_array = np.array(img)

    # Preprocess: perspective correction + contrast/sharpness enhancement
    img_array = preprocess_card(img_array)
    img_h, img_w = img_array.shape[:2]

    if lang == "auto":
        # Run both engines — JA reads kanji/kana/Latin, EN reads Latin with
        # higher accuracy on English card fonts. We merge the signals.
        # Running EN-only first and then detecting from its output (the old
        # approach) never detected JA, because the EN model returns empty /
        # Latin-garbage for JA-script regions — `detect_language` sees no
        # JA Unicode and stays on "en".
        result_en = ocr_en.ocr(img_array, cls=True)
        result_ja = ocr_ja.ocr(img_array, cls=True)

        def _annotate(result):
            out = []
            if result and result[0]:
                for line in result[0]:
                    pos = get_relative_position(line[0], img_w, img_h)
                    region = classify_region(pos)
                    out.append({"text": line[1][0], "region": region})
            return out

        en_annotated = _annotate(result_en)
        ja_annotated = _annotate(result_ja)

        # Detect primarily from the JA engine — it sees the actual script.
        # Fall back to EN annotations only when the JA engine returned nothing.
        detected = detect_language(ja_annotated or en_annotated)

        # Thai heuristic: PaddleOCR has no TH model, so `detect_language` will
        # never say "th" — the EN/JA engines can't output Thai Unicode. If the
        # name region came back (nearly) empty but the number region was read,
        # the card is probably printed in a script neither engine handles →
        # treat as Thai so the client searches the TH catalog.
        if detected == "en":
            name_chars = sum(
                len(t["text"].strip())
                for t in en_annotated + ja_annotated
                if t.get("region") == "name"
            )
            number_chars = sum(
                len(t["text"].strip())
                for t in en_annotated + ja_annotated
                if t.get("region") == "number"
            )
            if name_chars < 3 and number_chars >= 2:
                detected = "th"

        # Pick the result to return based on the detected language.
        if detected == "ja" and result_ja and result_ja[0]:
            # Merge JA + EN — JA for the name, EN for the (Latin) number/set.
            if result_en and result_en[0]:
                result = [deduplicate_results(list(result_ja[0]) + list(result_en[0]))]
            else:
                result = result_ja
        else:
            # EN or TH — TH uses the EN engine regardless (no Thai model).
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
