/**
 * Detect a Pokemon card in a photo and return a tight crop, so downstream
 * OCR / visual embedding doesn't waste resolution on the background.
 *
 * No heavy dependencies (no opencv.js) — pure canvas + pixel math:
 *   1. Downscale to ~400px wide for analysis
 *   2. Sobel edge-magnitude map
 *   3. Threshold = 1.5× mean edge magnitude
 *   4. Row/column projections of the thresholded edges
 *   5. Trim borders where projection falls below a minimum density
 *   6. Validate bbox (size, aspect ratio close to 2.5:3.5 ≈ 0.714)
 *   7. Scale bbox back to original image coords + crop with small pad
 *
 * If detection is not confident (bbox fails sanity checks), we return the
 * original blob so the pipeline degrades gracefully instead of cropping junk.
 */

const ANALYSIS_WIDTH = 400;
const POKEMON_ASPECT = 2.5 / 3.5; // ≈ 0.714
const ASPECT_TOLERANCE = 0.35;    // accept bbox ratios 0.36–1.07
const MIN_AREA_FRACTION = 0.25;   // bbox must cover ≥ 25% of analysis canvas
const CROP_PAD_FRACTION = 0.015;  // 1.5% pad around detected bbox

interface BBox { x: number; y: number; w: number; h: number }

export interface CardCropResult {
  blob: Blob;
  detected: boolean;       // true if a card bbox was confidently found
  cropWidth: number;
  cropHeight: number;
}

/**
 * Find the card in `input` and return a tight-cropped Blob. If detection
 * fails the original blob is returned untouched (detected=false).
 */
export async function detectAndCropCard(input: File | Blob): Promise<CardCropResult> {
  let img: HTMLImageElement;
  try {
    img = await blobToImage(input);
  } catch {
    return { blob: input, detected: false, cropWidth: 0, cropHeight: 0 };
  }

  const srcW = img.naturalWidth || img.width;
  const srcH = img.naturalHeight || img.height;
  if (!srcW || !srcH) {
    return { blob: input, detected: false, cropWidth: 0, cropHeight: 0 };
  }

  // Downscale analysis canvas — faster and smooths out JPEG noise.
  const analysisScale = Math.min(1, ANALYSIS_WIDTH / srcW);
  const aW = Math.max(32, Math.floor(srcW * analysisScale));
  const aH = Math.max(32, Math.floor(srcH * analysisScale));

  const small = document.createElement('canvas');
  small.width = aW;
  small.height = aH;
  const sctx = small.getContext('2d', { willReadFrequently: true });
  if (!sctx) return { blob: input, detected: false, cropWidth: 0, cropHeight: 0 };
  sctx.drawImage(img, 0, 0, aW, aH);
  const { data } = sctx.getImageData(0, 0, aW, aH);

  const edges = sobelMagnitude(data, aW, aH);
  const bbox = findEdgeBoundingBox(edges, aW, aH);
  if (!bbox) {
    return { blob: input, detected: false, cropWidth: srcW, cropHeight: srcH };
  }

  // Scale bbox back to source resolution, then pad slightly.
  const invScale = 1 / analysisScale;
  const padX = Math.floor(bbox.w * invScale * CROP_PAD_FRACTION);
  const padY = Math.floor(bbox.h * invScale * CROP_PAD_FRACTION);

  const cx = Math.max(0, Math.floor(bbox.x * invScale) - padX);
  const cy = Math.max(0, Math.floor(bbox.y * invScale) - padY);
  const cw = Math.min(srcW - cx, Math.floor(bbox.w * invScale) + 2 * padX);
  const ch = Math.min(srcH - cy, Math.floor(bbox.h * invScale) + 2 * padY);

  const out = document.createElement('canvas');
  out.width = cw;
  out.height = ch;
  const octx = out.getContext('2d');
  if (!octx) return { blob: input, detected: false, cropWidth: srcW, cropHeight: srcH };
  octx.drawImage(img, cx, cy, cw, ch, 0, 0, cw, ch);

  const cropped: Blob = await new Promise((resolve, reject) => {
    out.toBlob(
      b => (b ? resolve(b) : reject(new Error('card crop toBlob failed'))),
      'image/jpeg',
      0.93,
    );
  });

  return { blob: cropped, detected: true, cropWidth: cw, cropHeight: ch };
}

// ── Sobel edge magnitude ────────────────────────────────────────────────────

function sobelMagnitude(rgba: Uint8ClampedArray, w: number, h: number): Float32Array {
  // Grayscale first (rec. 601 luma weights)
  const gray = new Uint8ClampedArray(w * h);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j++) {
    gray[j] = (0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]) | 0;
  }

  const mag = new Float32Array(w * h);
  // Skip 1-pixel border so we don't read out-of-bounds.
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      // Sobel 3×3 kernels
      const gx =
        -gray[i - w - 1] + gray[i - w + 1]
        - 2 * gray[i - 1] + 2 * gray[i + 1]
        - gray[i + w - 1] + gray[i + w + 1];
      const gy =
        -gray[i - w - 1] - 2 * gray[i - w] - gray[i - w + 1]
        + gray[i + w - 1] + 2 * gray[i + w] + gray[i + w + 1];
      mag[i] = Math.hypot(gx, gy);
    }
  }
  return mag;
}

// ── Edge-based bounding box ────────────────────────────────────────────────

function findEdgeBoundingBox(edges: Float32Array, w: number, h: number): BBox | null {
  // Threshold = 1.5× mean edge magnitude (ignoring the border we skipped).
  let sum = 0;
  let count = 0;
  for (let i = 0; i < edges.length; i++) {
    if (edges[i] > 0) { sum += edges[i]; count++; }
  }
  if (count === 0) return null;
  const threshold = (sum / count) * 1.5;

  // Row + column projections of thresholded edges.
  const rowCounts = new Uint32Array(h);
  const colCounts = new Uint32Array(w);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (edges[y * w + x] >= threshold) {
        rowCounts[y]++;
        colCounts[x]++;
      }
    }
  }

  // A row that's part of the card must contain at least this many edge pixels.
  const rowMin = Math.max(3, Math.floor(w * 0.04));
  const colMin = Math.max(3, Math.floor(h * 0.04));

  let top = 0;
  while (top < h && rowCounts[top] < rowMin) top++;
  let bottom = h - 1;
  while (bottom > top && rowCounts[bottom] < rowMin) bottom--;
  let left = 0;
  while (left < w && colCounts[left] < colMin) left++;
  let right = w - 1;
  while (right > left && colCounts[right] < colMin) right--;

  const bw = right - left;
  const bh = bottom - top;
  if (bw < 10 || bh < 10) return null;

  // Sanity: area must be a meaningful fraction of the frame.
  const area = bw * bh;
  if (area < w * h * MIN_AREA_FRACTION) return null;

  // Sanity: aspect ratio should be near the Pokemon card ratio. Accept
  // portrait and landscape (some users rotate the phone).
  const ratio = bw / bh;
  const invRatio = bh / bw;
  const bestRatioDist = Math.min(
    Math.abs(ratio - POKEMON_ASPECT),
    Math.abs(invRatio - POKEMON_ASPECT),
  );
  if (bestRatioDist > ASPECT_TOLERANCE) return null;

  return { x: left, y: top, w: bw, h: bh };
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function blobToImage(blob: File | Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('image load failed')); };
    img.src = url;
  });
}
