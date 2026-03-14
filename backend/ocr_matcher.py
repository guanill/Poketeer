"""
ocr_matcher.py — OCR-based Pokémon card identification.

Pipeline:
  1. Crop the top ~18% of the card (where the name lives)
  2. Run EasyOCR on the crop
  3. Fuzzy-match the extracted text against the local card name list
  4. Return ranked matches

The card name list (card_names.json) is produced by build_index.py.
No external API calls are made at scan time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
import io

if TYPE_CHECKING:
    import easyocr

NAMES_PATH = Path(__file__).parent / "card_names.json"

# EasyOCR reader is expensive to initialise — cache it
_READER: "easyocr.Reader | None" = None
_CARD_NAMES: list[dict] | None = None

# Name → list of card dicts (multiple cards can share a name, e.g. different sets)
_NAME_INDEX: dict[str, list[dict]] | None = None


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _get_reader() -> "easyocr.Reader":
    global _READER
    if _READER is None:
        import easyocr  # lazy import — large dependency
        print("[OCR] Loading EasyOCR model (first run may take a moment)...")
        _READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _READER


def prewarm() -> None:
    """Pre-warm EasyOCR so the first scan is not slow."""
    import numpy as np
    reader = _get_reader()
    # Feed a tiny blank image to initialise internal state
    dummy = np.zeros((40, 200, 3), dtype=np.uint8)
    reader.readtext(dummy, detail=False, beamWidth=1)
    print("[OCR] EasyOCR pre-warmed.")


def load_card_names() -> None:
    """Load card names from the JSON file built by build_index.py."""
    global _CARD_NAMES, _NAME_INDEX
    if not NAMES_PATH.exists():
        return
    with open(NAMES_PATH, encoding="utf-8") as f:
        _CARD_NAMES = json.load(f)

    _NAME_INDEX = {}
    for card in _CARD_NAMES:
        key = card["name"].lower()
        _NAME_INDEX.setdefault(key, []).append(card)


def is_ready() -> bool:
    return _CARD_NAMES is not None and len(_CARD_NAMES) > 0


# ---------------------------------------------------------------------------
# OCR + fuzzy matching
# ---------------------------------------------------------------------------

def _crop_name_region(image_bytes: bytes) -> bytes:
    """
    Return the top 18% of the card image as JPEG bytes.
    The Pokémon card name is always printed in this band.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    crop_h = max(40, int(h * 0.18))
    cropped = img.crop((0, 0, w, crop_h))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def ocr_matches(image_bytes: bytes, top_k: int = 5) -> list[dict]:
    """
    Run OCR on the card image, fuzzy-match against card names,
    return up to top_k matches with a 'confidence' field (0-1).
    """
    if not is_ready():
        return []

    from rapidfuzz import process, fuzz

    # Extract text from the name region
    crop_bytes = _crop_name_region(image_bytes)
    reader = _get_reader()

    try:
        results = reader.readtext(crop_bytes, detail=True, paragraph=False,
                                  beamWidth=1)  # beamWidth=1 is ~3x faster
    except Exception:
        return []

    # Collect all text fragments, prefer longer / higher-confidence ones
    texts = [
        (text.strip(), conf)
        for (_, text, conf) in results
        if text.strip() and conf > 0.2
    ]

    if not texts:
        return []

    # Use the highest-confidence fragment as the query
    texts.sort(key=lambda x: -x[1])
    query = texts[0][0]
    ocr_confidence = texts[0][1]

    # Fuzzy match against all known card names
    all_names = list(_NAME_INDEX.keys())  # type: ignore[union-attr]
    hits = process.extract(
        query.lower(),
        all_names,
        scorer=fuzz.WRatio,
        limit=top_k * 3,   # fetch extra, deduplicate later
    )

    seen_ids: set[str] = set()
    matches: list[dict] = []

    for matched_name, score, _ in hits:
        fuzzy_conf = score / 100.0
        combined_conf = fuzzy_conf * min(ocr_confidence + 0.2, 1.0)

        for card in _NAME_INDEX[matched_name]:  # type: ignore[index]
            if card["id"] in seen_ids:
                continue
            seen_ids.add(card["id"])
            matches.append({**card, "confidence": round(combined_conf, 4)})
            if len(matches) >= top_k:
                break
        if len(matches) >= top_k:
            break

    return matches
