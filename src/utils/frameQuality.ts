/**
 * Live-frame quality analysis for the card scanner camera feed.
 *
 * Three signals detected on a downscaled greyscale sample of the card-guide
 * area. All computed from one already-collected `ImageData`, so sampling a
 * frame costs one `drawImage` + three short passes over the pixel array.
 *
 * Consumer can read each flag independently to show UI chips and/or gate
 * auto-scan. A frame is considered capturable when all three are "ok".
 */

export interface FrameQuality {
  brightness: number;   // 0–255 mean luma
  glareRatio: number;   // 0–1  fraction of pixels > 245 luma
  blurScore: number;    // 0–∞ higher = sharper (Laplacian variance)
  tooDark: boolean;
  tooBright: boolean;
  hasGlare: boolean;
  tooBlurry: boolean;
  /** True when none of the above flags trip. */
  ok: boolean;
}

// Thresholds tuned for mobile camera luma at ~256-px sample resolution.
const DARK_THRESHOLD = 55;
const BRIGHT_THRESHOLD = 220;
const GLARE_RATIO_THRESHOLD = 0.045;  // >4.5% blown-out pixels
const BLUR_VARIANCE_THRESHOLD = 90;   // lower = blurry

/**
 * Analyse a greyscale patch of the guide area. Call with the RGBA data from
 * the small detection canvas that `CardScanner` already builds for auto-scan.
 */
export function analyseFrameQuality(
  rgba: Uint8ClampedArray,
  w: number,
  h: number,
): FrameQuality {
  const px = w * h;
  if (px === 0) {
    return {
      brightness: 0, glareRatio: 0, blurScore: 0,
      tooDark: true, tooBright: false, hasGlare: false, tooBlurry: true,
      ok: false,
    };
  }

  // Greyscale pass: collect luma + glare count in one go.
  const gray = new Uint8ClampedArray(px);
  let lumaSum = 0;
  let glareCount = 0;
  for (let i = 0, j = 0; i < rgba.length; i += 4, j++) {
    const g = (0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]) | 0;
    gray[j] = g;
    lumaSum += g;
    if (g > 245) glareCount++;
  }
  const brightness = lumaSum / px;
  const glareRatio = glareCount / px;

  // Laplacian variance — classic focus measure. Skip 1-px border.
  let lapSum = 0;
  let lapSumSq = 0;
  let lapCount = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const l = -4 * gray[i] + gray[i - 1] + gray[i + 1] + gray[i - w] + gray[i + w];
      lapSum += l;
      lapSumSq += l * l;
      lapCount++;
    }
  }
  const lapMean = lapCount ? lapSum / lapCount : 0;
  const blurScore = lapCount ? Math.max(0, lapSumSq / lapCount - lapMean * lapMean) : 0;

  const tooDark = brightness < DARK_THRESHOLD;
  const tooBright = brightness > BRIGHT_THRESHOLD;
  const hasGlare = glareRatio > GLARE_RATIO_THRESHOLD;
  const tooBlurry = blurScore < BLUR_VARIANCE_THRESHOLD;
  const ok = !tooDark && !tooBright && !hasGlare && !tooBlurry;

  return { brightness, glareRatio, blurScore, tooDark, tooBright, hasGlare, tooBlurry, ok };
}
