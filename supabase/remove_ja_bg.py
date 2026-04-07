"""
remove_ja_bg.py — Remove white backgrounds from Japanese set pack art images.

Downloads each JA set's logo_url, flood-fills white from corners to make
transparent, uploads the result to Supabase Storage, and updates logo_url.
"""

import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import requests
from dotenv import load_dotenv
from PIL import Image
from scipy import ndimage
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

BUCKET = "set-logos"
TOLERANCE = 40  # Per-channel distance from 255 to still count as "white"
MAX_DIM = 800   # Resize large images to this max dimension before processing


def remove_white_bg(img: Image.Image, tolerance: int = TOLERANCE) -> Image.Image:
    """
    Remove white background using numpy + scipy label-based flood fill.
    Much faster than pixel-by-pixel BFS for large images.
    """
    # Resize if too large (speeds up processing enormously)
    orig_size = img.size
    w, h = img.size
    if max(w, h) > MAX_DIM:
        scale = MAX_DIM / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    img = img.convert("RGBA")
    arr = np.array(img)
    w, h = img.size

    # Build a mask of "white-ish" pixels
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    white_mask = (
        (r.astype(int) > 255 - tolerance)
        & (g.astype(int) > 255 - tolerance)
        & (b.astype(int) > 255 - tolerance)
    )

    # Label connected components of white pixels
    labeled, num_features = ndimage.label(white_mask)

    # Find which labels touch the image border (those are background)
    border_labels = set()
    border_labels.update(labeled[0, :].tolist())       # top row
    border_labels.update(labeled[-1, :].tolist())      # bottom row
    border_labels.update(labeled[:, 0].tolist())       # left col
    border_labels.update(labeled[:, -1].tolist())      # right col
    border_labels.discard(0)  # 0 = non-white pixels

    # Create transparency mask: border-connected white → transparent
    bg_mask = np.isin(labeled, list(border_labels))
    arr[bg_mask, 3] = 0  # Set alpha to 0

    return Image.fromarray(arr)


def ensure_bucket():
    """Create the storage bucket if it doesn't exist."""
    try:
        sb.storage.get_bucket(BUCKET)
        print(f"  Bucket '{BUCKET}' exists")
    except Exception:
        try:
            sb.storage.create_bucket(BUCKET, options={"public": True})
            print(f"  Created bucket '{BUCKET}'")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  Bucket '{BUCKET}' already exists")
            else:
                print(f"  Warning: bucket creation: {e}")


def main():
    print("=" * 60)
    print("Removing white backgrounds from JA set pack art")
    print("=" * 60)

    ensure_bucket()

    # Get all JA sets with logo_url
    res = sb.table("sets").select("id, name, logo_url").eq("language", "ja").execute()
    ja_sets = [s for s in (res.data or []) if s.get("logo_url")]
    print(f"\nJA sets with logo_url: {len(ja_sets)}")

    # Filter to only pokemon-card.com images (skip already-processed ones)
    to_process = [
        s for s in ja_sets
        if "pokemon-card.com" in (s["logo_url"] or "")
        or "asia.pokemon-card.com" in (s["logo_url"] or "")
    ]
    print(f"Sets with pokemon-card.com images: {len(to_process)}\n")

    updated = 0
    errors = 0

    for s in to_process:
        set_id = s["id"]
        name = s["name"]
        url = s["logo_url"]
        filename = f"{set_id}.png"

        try:
            # Download
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                print(f"  SKIP {set_id:15s} | HTTP {r.status_code}")
                errors += 1
                continue

            # Open and process
            img = Image.open(io.BytesIO(r.content))
            img_transparent = remove_white_bg(img)

            # Save to bytes
            buf = io.BytesIO()
            img_transparent.save(buf, format="PNG", optimize=True)
            buf.seek(0)
            png_bytes = buf.getvalue()

            # Upload to Supabase Storage
            storage_path = f"ja/{filename}"
            try:
                sb.storage.from_(BUCKET).remove([storage_path])
            except Exception:
                pass

            sb.storage.from_(BUCKET).upload(
                storage_path,
                png_bytes,
                file_options={"content-type": "image/png", "upsert": "true"},
            )

            # Get public URL
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"

            # Update DB
            sb.table("sets").update({"logo_url": public_url}).eq("id", set_id).execute()

            print(f"  OK   {set_id:15s} | {name[:30]:30s} | {img.size[0]}x{img.size[1]}")
            updated += 1

        except Exception as e:
            print(f"  ERR  {set_id:15s} | {e}")
            errors += 1

    print(f"\nDone! Updated: {updated}, Errors: {errors}")


if __name__ == "__main__":
    main()
