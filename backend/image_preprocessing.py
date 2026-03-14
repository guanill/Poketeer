"""
image_preprocessing.py — Image preprocessing to improve card identification accuracy.

Preprocessing steps:
  1. Auto-orientation  — fix EXIF rotation from phone cameras
  2. White-balance     — neutralise colour cast from lighting
  3. Contrast stretch  — normalise exposure for consistent features
  4. Sharpening        — recover detail from blurry phone photos
  5. Perspective warp  — (optional) correct skew when card edges are detected

These transforms run *before* the feature extractor, so both ResNet50 and OCR
receive a cleaner, more normalised input.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


# ---------------------------------------------------------------------------
# Core transforms
# ---------------------------------------------------------------------------

def auto_orient(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation tag, then strip metadata."""
    return ImageOps.exif_transpose(img)


def white_balance(img: Image.Image) -> Image.Image:
    """
    Simple gray-world white-balance.
    Shifts per-channel means toward the overall mean brightness.
    """
    arr = np.array(img, dtype=np.float32)
    avg_per_channel = arr.mean(axis=(0, 1))  # (3,)
    overall_avg = avg_per_channel.mean()

    if (avg_per_channel < 1).any():
        return img  # avoid divide-by-zero on nearly-black images

    scale = overall_avg / avg_per_channel  # (3,)
    arr = np.clip(arr * scale[np.newaxis, np.newaxis, :], 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def contrast_stretch(img: Image.Image, low_pct: float = 1.0, high_pct: float = 99.0) -> Image.Image:
    """
    Linear contrast stretch: maps the low_pct–high_pct intensity range to 0–255.
    Removes dim/washed-out images without blowing highlights.
    """
    arr = np.array(img, dtype=np.float32)
    lo = np.percentile(arr, low_pct)
    hi = np.percentile(arr, high_pct)
    if hi - lo < 10:
        return img  # already good contrast
    arr = (arr - lo) / (hi - lo) * 255.0
    arr = np.clip(arr, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def sharpen(img: Image.Image, factor: float = 1.3) -> Image.Image:
    """Mild sharpening to recover detail from phone camera blur."""
    enhancer = ImageEnhance.Sharpness(img)
    return enhancer.enhance(factor)


def denoise(img: Image.Image) -> Image.Image:
    """Light median filter to reduce JPEG artifacts and sensor noise."""
    return img.filter(ImageFilter.MedianFilter(size=3))


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------

def preprocess(image_bytes: bytes, for_ocr: bool = False) -> bytes:
    """
    Run the full preprocessing pipeline on raw image bytes.
    Returns cleaned JPEG bytes ready for feature extraction or OCR.

    Parameters
    ----------
    image_bytes : raw JPEG/PNG/WEBP bytes
    for_ocr : if True, applies extra contrast for text readability
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # 1. Fix phone camera orientation
    img = auto_orient(img)

    # 2. White-balance colour cast
    img = white_balance(img)

    # 3. Contrast normalisation
    if for_ocr:
        img = contrast_stretch(img, low_pct=0.5, high_pct=99.5)
    else:
        img = contrast_stretch(img)

    # 4. Light denoising (only if image is large enough)
    w, h = img.size
    if w > 300 and h > 300:
        img = denoise(img)

    # 5. Sharpen
    img = sharpen(img, factor=1.5 if for_ocr else 1.2)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def preprocess_for_visual(image_bytes: bytes) -> bytes:
    """Preprocess optimised for visual feature extraction."""
    return preprocess(image_bytes, for_ocr=False)


def preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """Preprocess optimised for OCR text extraction."""
    return preprocess(image_bytes, for_ocr=True)


# ---------------------------------------------------------------------------
# Test-time augmentation (TTA) for better visual matching
# ---------------------------------------------------------------------------

def generate_augmentations(image_bytes: bytes, n: int = 3) -> list[bytes]:
    """
    Generate n augmented versions of the image for test-time augmentation.
    The identification pipeline can extract features from each augmentation
    and average them for a more robust match.

    Augmentations:
      - Original (preprocessed)
      - Slight brightness variation
      - Slight rotation
      - Horizontal crop variation
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = auto_orient(img)

    augmented = []

    # Base preprocessed version
    augmented.append(_to_bytes(img))

    if n >= 2:
        # Slightly brighter
        bright = ImageEnhance.Brightness(img).enhance(1.15)
        augmented.append(_to_bytes(bright))

    if n >= 3:
        # Slightly darker
        dark = ImageEnhance.Brightness(img).enhance(0.85)
        augmented.append(_to_bytes(dark))

    if n >= 4:
        # Higher contrast
        contrast = ImageEnhance.Contrast(img).enhance(1.2)
        augmented.append(_to_bytes(contrast))

    if n >= 5:
        # Center crop (90% of image)
        w, h = img.size
        margin_x = int(w * 0.05)
        margin_y = int(h * 0.05)
        cropped = img.crop((margin_x, margin_y, w - margin_x, h - margin_y))
        augmented.append(_to_bytes(cropped))

    return augmented[:n]


def _to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
