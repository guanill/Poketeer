/**
 * Native on-device card scanner.
 *
 * Pipeline:
 *  1. Crop the image into TWO regions:
 *     a. Top 22%  -> card name (fuzzy-matched against catalog)
 *     b. Bottom 12% -> card number ("4/102", "025/172", "SWSH025")
 *  2. Multiple preprocessing passes with different contrast/brightness levels
 *     to handle foil, holo, full-art, and normal card surfaces
 *  3. Tesseract.js OCR on both crops (worker + data bundled in APK)
 *  4. Number lookup (most accurate) -> name fuzzy-match fallback -- 100% offline
 *
 *  If a backend URL is configured and reachable, uses the server's
 *  ResNet50 + EasyOCR pipeline instead (much more accurate).
 */
import { createWorker } from 'tesseract.js';
import type { ScanMatch, ScanResult } from './cardScanService';
import { catalogService } from './catalogService';
import { visualMatchService } from './visualMatchService';

export type { ScanMatch, ScanResult };

// ── Backend fallback (optional — used when phone is on same network as PC) ───
let _backendUrl: string | null = null;
let _backendReachable: boolean | null = null;

/** Call once at app startup or from settings to enable backend scanning. */
export function setBackendUrl(url: string | null) {
  _backendUrl = url;
  _backendReachable = null; // reset — will be re-probed on next scan
}

export function getBackendUrl(): string | null {
  return _backendUrl;
}

async function tryBackendScan(imageFile: File | Blob, topK: number): Promise<ScanResult | null> {
  if (!_backendUrl) return null;

  // Probe once per session
  if (_backendReachable === null) {
    try {
      const res = await fetch(`${_backendUrl}/health`, { signal: AbortSignal.timeout(2000) });
      _backendReachable = res.ok;
    } catch {
      _backendReachable = false;
    }
  }
  if (!_backendReachable) return null;

  try {
    const formData = new FormData();
    formData.append('image', imageFile);
    const res = await fetch(`${_backendUrl}/scan?top_k=${topK}`, {
      method: 'POST',
      body: formData,
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ── Image preprocessing ───────────────────────────────────────────────────────

const NAME_CROP_PCT = 0.22;

interface PreprocessProfile {
  label: string;
  filter: string;
}

// Multiple profiles to handle different card surfaces
const NAME_PROFILES: PreprocessProfile[] = [
  { label: 'balanced',  filter: 'grayscale(1) contrast(1.8) brightness(1.1)' },
  { label: 'high-contrast', filter: 'grayscale(1) contrast(2.8) brightness(1.2)' },
  { label: 'low-contrast',  filter: 'grayscale(1) contrast(1.3) brightness(1.0)' },
];

const BOTTOM_PROFILES: PreprocessProfile[] = [
  { label: 'balanced',  filter: 'grayscale(1) contrast(2.5) brightness(1.15)' },
  { label: 'high-contrast', filter: 'grayscale(1) contrast(3.5) brightness(1.3)' },
];

function cropAndFilter(
  imageFile: File | Blob,
  cropTop: number,
  cropBottom: number,
  filter: string,
  scale: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(imageFile);

    img.onload = () => {
      URL.revokeObjectURL(url);
      const srcW = img.naturalWidth || img.width;
      const srcH = img.naturalHeight || img.height;
      const cropY = Math.floor(srcH * cropTop);
      const cropH = Math.floor(srcH * cropBottom) - cropY;

      const canvas = document.createElement('canvas');
      canvas.width = srcW * scale;
      canvas.height = cropH * scale;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('No canvas 2d context')); return; }

      ctx.filter = filter;
      ctx.drawImage(img, 0, cropY, srcW, cropH, 0, 0, canvas.width, canvas.height);

      canvas.toBlob(
        blob => blob ? resolve(blob) : reject(new Error('canvas.toBlob failed')),
        'image/png',
      );
    };

    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Image load failed')); };
    img.src = url;
  });
}

function preprocessName(imageFile: File | Blob, profile: PreprocessProfile): Promise<Blob> {
  return cropAndFilter(imageFile, 0, NAME_CROP_PCT, profile.filter, 2);
}

function preprocessBottom(imageFile: File | Blob, profile: PreprocessProfile): Promise<Blob> {
  return cropAndFilter(imageFile, 1 - 0.12, 1, profile.filter, 3);
}

// ── Tesseract worker ─────────────────────────────────────────────────────────
let _workerPromise: ReturnType<typeof createWorker> | null = null;

function getWorker() {
  if (!_workerPromise) {
    _workerPromise = createWorker('eng', 1, {
      workerPath: '/tesseract-worker.min.js',
      corePath: '/tesseract-core.wasm.js',
      langPath: '/lang',
      logger: () => {},
    }).catch(err => {
      console.error('[nativeScan] Tesseract worker init failed:', err);
      _workerPromise = null;
      throw err;
    });
  }
  return _workerPromise;
}

// ── Text extraction ───────────────────────────────────────────────────────────
const STOP_WORDS = new Set([
  'hp', 'stage', 'basic', 'level', 'lv', 'ex', 'gx', 'vmax', 'vstar', 'v',
  'pokemon', 'trainer', 'energy', 'item', 'tool', 'supporter', 'stadium',
  'weakness', 'resistance', 'retreat', 'evolves', 'from', 'put', 'this',
  'card', 'your', 'the', 'and', 'damage', 'discard', 'attach', 'flip',
  'player', 'each', 'once', 'during', 'turn', 'hand', 'deck', 'bench',
]);

// Common OCR misreads for Pokemon card names
const OCR_CORRECTIONS: Record<string, string> = {
  'pikachu': 'pikachu',
  'charizard': 'charizard',
  '0': 'o', '1': 'l', '5': 's',
};

function cleanOcrText(raw: string): string {
  // Fix common single-char OCR misreads in the context of names
  let text = raw;
  // Remove stray digits mixed into words (e.g. "Pik4chu" -> "Pikachu")
  text = text.replace(/([a-zA-Z])(\d)([a-zA-Z])/g, (_, a, d, b) => {
    const fix = OCR_CORRECTIONS[d] || '';
    return a + fix + b;
  });
  return text;
}

function extractNameCandidates(rawText: string): string[] {
  const candidates: string[] = [];
  const cleaned = cleanOcrText(rawText);

  const lines = cleaned
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length >= 2 && l.length <= 50);

  for (const line of lines.slice(0, 8)) {
    // Keep only letters, spaces, hyphens, apostrophes, periods
    const norm = line.replace(/[^a-zA-Z\u00C0-\u024F\s'.\-]/g, ' ').replace(/\s+/g, ' ').trim();
    if (norm.length < 2) continue;

    const words = norm.toLowerCase().split(' ').filter(w => w.length > 0);
    if (words.length === 0) continue;

    const meaningful = words.filter(w => w.length > 1 && !STOP_WORDS.has(w));
    if (meaningful.length === 0) continue;

    candidates.push(meaningful.join(' '));
  }

  // Also try the full first line as-is (sometimes the whole line IS the name)
  if (lines.length > 0) {
    const firstLine = lines[0].replace(/[^a-zA-Z\u00C0-\u024F\s'.\-]/g, '').trim();
    if (firstLine.length >= 3) candidates.push(firstLine.toLowerCase());
  }

  return [...new Set(candidates)];
}

// ── Card-number extraction ────────────────────────────────────────────────────
function extractCardNumber(ocrText: string): string | null {
  // Pattern A: "4/102", "025/172", "TG30/TG30", "SV101/SV190"
  const slashMatch = ocrText.match(/([A-Z]{0,4}\d{1,4})\s*[/\\|]\s*[A-Z0-9]+/i);
  if (slashMatch) {
    return slashMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();
  }

  // Pattern B: standalone promo codes like "SWSH025", "XY-P", "S-P"
  const promoMatch = ocrText.match(/\b([A-Z]{2,4}\d{3,4})\b/i);
  if (promoMatch) {
    return promoMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();
  }

  // Pattern C: just a number like "025" or "4" near a slash-like char
  const bareNum = ocrText.match(/\b(\d{1,4})\s*[/\\|]/);
  if (bareNum) {
    return bareNum[1].replace(/^0+(?=\d)/, '');
  }

  return null;
}

// ── Multi-pass OCR ────────────────────────────────────────────────────────────

interface OcrPassResult {
  text: string;
  confidence: number;
}

async function ocrMultiPass(
  imageFile: File | Blob,
  profiles: PreprocessProfile[],
  cropFn: (file: File | Blob, profile: PreprocessProfile) => Promise<Blob>,
): Promise<OcrPassResult> {
  const worker = await getWorker();
  let bestResult: OcrPassResult = { text: '', confidence: 0 };

  for (const profile of profiles) {
    try {
      const blob = await cropFn(imageFile, profile);
      const result = await worker.recognize(blob);
      const text = result.data.text ?? '';
      const conf = result.data.confidence ?? 0;

      if (conf > bestResult.confidence && text.trim().length > 0) {
        bestResult = { text, confidence: conf };
      }

      // If confidence is very high, no need to try more profiles
      if (conf > 80) break;
    } catch {
      // Continue to next profile
    }
  }

  return bestResult;
}

// ── Merge OCR + Visual results ────────────────────────────────────────────────

function mergeResults(ocrMatches: ScanMatch[], visualMatches: ScanMatch[], topK: number): ScanMatch[] {
  const merged = new Map<string, ScanMatch>();

  // Visual matches are the primary signal
  for (const m of visualMatches) {
    merged.set(m.id, { ...m, method: 'visual' });
  }

  // OCR matches boost confidence if they agree, or add new candidates
  for (const m of ocrMatches) {
    const existing = merged.get(m.id);
    if (existing) {
      // Both OCR and visual agree -- boost confidence significantly
      existing.confidence = Math.min(0.99, existing.confidence + m.confidence * 0.3);
      existing.method = 'ocr+visual';
    } else {
      merged.set(m.id, { ...m });
    }
  }

  return [...merged.values()]
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, topK);
}

// ── Main scan ─────────────────────────────────────────────────────────────────
export async function nativeScanCard(imageFile: File | Blob, topK = 5): Promise<ScanResult> {
  // Try backend first if configured (much more accurate)
  const backendResult = await tryBackendScan(imageFile, topK);
  if (backendResult && backendResult.matches.length > 0) {
    return backendResult;
  }

  // Run visual matching and OCR in parallel
  const visualPromise = visualMatchService.isReady()
    ? visualMatchService.matchCard(imageFile, topK * 2).catch(() => [] as ScanMatch[])
    : Promise.resolve([] as ScanMatch[]);

  const ocrPromise = (async () => {
    const [nameResult, bottomResult] = await Promise.all([
      ocrMultiPass(imageFile, NAME_PROFILES, preprocessName),
      ocrMultiPass(imageFile, BOTTOM_PROFILES, preprocessBottom),
    ]);

    const ocrText = nameResult.text;
    const bottomText = bottomResult.text;
    const cardNumber = extractCardNumber(bottomText) || extractCardNumber(ocrText);
    const nameCandidates = extractNameCandidates(ocrText);
    const nameHint = nameCandidates[0] ?? '';

    let ocrMatches: ScanMatch[] = [];

    if (cardNumber) {
      ocrMatches = await catalogService.searchByNumber(cardNumber, nameHint, topK);
    }

    if (ocrMatches.length === 0 && nameCandidates.length > 0) {
      let bestMatches: ScanMatch[] = [];
      let bestTopConfidence = 0;
      for (const candidate of nameCandidates.slice(0, 5)) {
        const results = await catalogService.fuzzySearchByName(candidate, topK);
        if (results.length > 0) {
          const topConf = results[0].confidence;
          if (topConf > bestTopConfidence) {
            bestMatches = results;
            bestTopConfidence = topConf;
          }
          if (topConf > 0.75) break;
        }
      }
      ocrMatches = bestMatches;
    }

    const combinedOcr = bottomText ? `${ocrText}\n[bottom] ${bottomText}` : ocrText;
    return { ocrMatches, ocrText: combinedOcr };
  })();

  const [visualMatches, { ocrMatches, ocrText }] = await Promise.all([
    visualPromise, ocrPromise,
  ]);

  // Merge results from both pipelines
  const matches = mergeResults(ocrMatches, visualMatches, topK);

  const methodUsed = visualMatches.length > 0 && ocrMatches.length > 0
    ? 'combined'
    : visualMatches.length > 0 ? 'visual' : ocrMatches.length > 0 ? 'ocr' : 'none';

  return {
    matches,
    ocr_text: ocrText,
    method_used: methodUsed as ScanResult['method_used'],
    visual_index_size: visualMatches.length,
    catalog_size: 0,
  };
}

export async function nativeCheckHealth(): Promise<boolean> {
  return true; // always available -- no backend needed
}
