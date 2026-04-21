"""Upload local foil-pack images to Supabase Storage and update set logo_url."""
import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
from dotenv import load_dotenv
from PIL import Image
from scipy import ndimage
from supabase import create_client

try:
    import pillow_avif  # noqa: F401  -- registers AVIF plugin if installed
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "set-logos"
TOLERANCE = 40
MAX_DIM = 800

DOWNLOADS = Path(r"C:\Users\guani\Downloads")

MAPPING: dict[str, tuple[str, str]] = {
    # filename: (set_id, bg_color_to_remove)
    "worldchampionsuhio oack.webp": ("PCG10-ja", "black"),
}


def remove_bg(img: Image.Image, color: str = "white", tolerance: int = TOLERANCE) -> Image.Image:
    """Flood-fill from borders to remove a uniform white or black background."""
    w, h = img.size
    if max(w, h) > MAX_DIM:
        scale = MAX_DIM / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img = img.convert("RGBA")
    arr = np.array(img)
    r, g, b = arr[:, :, 0].astype(int), arr[:, :, 1].astype(int), arr[:, :, 2].astype(int)
    if color == "black":
        mask = (r < tolerance) & (g < tolerance) & (b < tolerance)
    else:  # white
        mask = (r > 255 - tolerance) & (g > 255 - tolerance) & (b > 255 - tolerance)
    labeled, _ = ndimage.label(mask)
    border = set()
    border.update(labeled[0, :].tolist())
    border.update(labeled[-1, :].tolist())
    border.update(labeled[:, 0].tolist())
    border.update(labeled[:, -1].tolist())
    border.discard(0)
    bg = np.isin(labeled, list(border))
    arr[bg, 3] = 0
    return Image.fromarray(arr)


def upload_one(fname: str, set_id: str, bg_color: str = "white"):
    src = DOWNLOADS / fname
    if not src.exists():
        print(f"  MISS  {set_id:10}  file not found: {src}")
        return False

    img = Image.open(src)
    processed = remove_bg(img, color=bg_color)

    buf = io.BytesIO()
    processed.save(buf, format="PNG", optimize=True)
    png = buf.getvalue()

    storage_path = f"ja/{set_id}.png"
    try:
        sb.storage.from_(BUCKET).remove([storage_path])
    except Exception:
        pass
    sb.storage.from_(BUCKET).upload(
        storage_path,
        png,
        file_options={"content-type": "image/png", "upsert": "true"},
    )
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"
    sb.table("sets").update({"logo_url": public_url}).eq("id", set_id).execute()
    print(f"  OK    {set_id:10}  {img.size[0]}x{img.size[1]}  <- {fname}")
    return True


if __name__ == "__main__":
    try:
        sb.storage.get_bucket(BUCKET)
    except Exception:
        sb.storage.create_bucket(BUCKET, options={"public": True})

    ok = 0
    for fname, (sid, bg) in MAPPING.items():
        try:
            if upload_one(fname, sid, bg):
                ok += 1
        except Exception as e:
            print(f"  ERR   {sid:10}  {e}")
    print(f"\nUploaded/updated: {ok}/{len(MAPPING)}")
