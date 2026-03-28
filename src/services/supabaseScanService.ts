/**
 * Supabase-backed card scanning.
 *
 * Pipeline:
 *   1. Crop top 25% of card image → multi-pass OCR the name (3 contrast profiles)
 *   2. Crop bottom 12% → multi-pass OCR the card number (2 profiles)
 *   3. Search by number first (most accurate), then fuzzy name search
 *   4. Optional: if cloud embedding model is up, boost/merge with visual matches
 */

import { supabase } from '../lib/supabase';
import type { ScanMatch, ScanResult, ScanLanguage } from './cardScanService';

// HF Space URL for optional visual embedding boost
const HF_SPACE_URL = 'https://agm3000-poketeer-card-embedder.hf.space';

// ── Image cropping ───────────────────────────────────────────────────────────

function cropRegion(
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

// Multiple preprocessing profiles to handle different card surfaces (foil, holo, normal)
const NAME_PROFILES = [
  { label: 'balanced',      filter: 'grayscale(1) contrast(1.8) brightness(1.1)' },
  { label: 'high-contrast', filter: 'grayscale(1) contrast(2.8) brightness(1.2)' },
  { label: 'low-contrast',  filter: 'grayscale(1) contrast(1.3) brightness(1.0)' },
];

const NUMBER_PROFILES = [
  { label: 'balanced',      filter: 'grayscale(1) contrast(2.5) brightness(1.15)' },
  { label: 'high-contrast', filter: 'grayscale(1) contrast(3.5) brightness(1.3)' },
  { label: 'inverted',      filter: 'grayscale(1) contrast(2.0) brightness(1.4) invert(1)' },
];

// ── Tesseract worker (reused across scans) ───────────────────────────────────

type TessWorker = Awaited<ReturnType<typeof import('tesseract.js')['createWorker']>>;
let _workerEn: TessWorker | null = null;
let _workerJa: TessWorker | null = null;

async function getWorker(lang: ScanLanguage): Promise<TessWorker> {
  const { createWorker } = await import('tesseract.js');

  if (lang === 'ja') {
    if (!_workerJa) _workerJa = await createWorker('jpn+eng');
    return _workerJa;
  }
  if (!_workerEn) _workerEn = await createWorker('eng');
  return _workerEn;
}

// ── Multi-pass OCR ───────────────────────────────────────────────────────────

interface OcrResult {
  text: string;
  confidence: number;
  /** The cropped+filtered image blob that produced the best result */
  cropBlob?: Blob;
}

/**
 * Try multiple contrast profiles on a cropped region and return the best OCR result.
 * Stops early if confidence > 80%.
 */
async function ocrMultiPass(
  imageFile: File | Blob,
  cropTop: number,
  cropBottom: number,
  scale: number,
  profiles: { label: string; filter: string }[],
  lang: ScanLanguage,
): Promise<OcrResult> {
  const worker = await getWorker(lang);
  let best: OcrResult = { text: '', confidence: 0 };

  for (const profile of profiles) {
    try {
      const blob = await cropRegion(imageFile, cropTop, cropBottom, profile.filter, scale);
      const { data } = await worker.recognize(blob);
      const text = (data.text ?? '').trim();
      const conf = data.confidence ?? 0;

      if (conf > best.confidence && text.length > 0) {
        best = { text, confidence: conf, cropBlob: blob };
      }

      // High confidence — no need to try more profiles
      if (conf > 80) break;
    } catch {
      // Continue to next profile
    }
  }

  return best;
}

// ── Text extraction helpers ──────────────────────────────────────────────────

/** Extract a card number like "4/102", "025/172", "SWSH025" from OCR text. */
function extractCardNumber(text: string): string | null {
  // Normalize common OCR misreads in number context
  const cleaned = text
    .replace(/[oO]/g, '0')   // O → 0 in number regions
    .replace(/[lI]/g, '1')   // l/I → 1
    .replace(/[sS]/g, '5')   // S → 5
    .replace(/[—–-]+/g, '/') // dashes → slash
    .replace(/\s+/g, ' ');

  // Pattern A: "4/102", "025/172", "TG30/TG30"
  const slashMatch = cleaned.match(/([A-Z]{0,4}\d{1,4})\s*[/\\|]\s*[A-Z0-9]+/i);
  if (slashMatch) return slashMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();

  // Pattern B: standalone promo codes like "SWSH025"
  const promoMatch = cleaned.match(/\b([A-Z]{2,4}\d{3,4})\b/i);
  if (promoMatch) return promoMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();

  // Pattern C: bare number near a slash
  const bareNum = cleaned.match(/\b(\d{1,4})\s*[/\\|]/);
  if (bareNum) return bareNum[1].replace(/^0+(?=\d)/, '');

  // Pattern D: just a number at the start/end of text (last resort)
  const anyNum = cleaned.match(/\b(\d{1,4})\b/);
  if (anyNum && anyNum[1].length >= 1) return anyNum[1].replace(/^0+(?=\d)/, '');

  return null;
}

/** Extract the card name from OCR text, handling both EN and JA. */
function extractNameQuery(text: string, lang: ScanLanguage): string {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  if (lines.length === 0) return '';

  if (lang === 'ja') {
    for (const line of lines.slice(0, 4)) {
      const clean = line
        .replace(/[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEFa-zA-Z\s'.\-]/g, '')
        .trim();
      if (clean.length >= 1) return clean;
    }
    return lines[0];
  }

  for (const line of lines.slice(0, 4)) {
    const clean = line.replace(/[^a-zA-Z\u00C0-\u024F\s'.\-]/g, ' ').replace(/\s+/g, ' ').trim();
    if (clean.length >= 2) return clean;
  }
  return lines[0];
}

// ── Supabase search helpers ──────────────────────────────────────────────────

/** Search cards by number + optional name hint. Tries multiple number formats. */
async function searchByNumber(
  cardNumber: string,
  nameHint: string,
  topK: number,
  lang: ScanLanguage,
): Promise<ScanMatch[]> {
  // Try the number as-is + zero-padded to 3 digits (e.g. "5" → "005", "25" → "025")
  const variants = new Set<string>([cardNumber]);
  const numOnly = cardNumber.replace(/\D/g, '');
  if (numOnly.length > 0) {
    variants.add(numOnly);
    variants.add(numOnly.padStart(3, '0'));
    variants.add(numOnly.padStart(2, '0'));
  }

  const langFilter = lang === 'ja' ? 'ja' : 'en';
  let allRows: Array<Record<string, unknown>> = [];

  for (const num of variants) {
    const { data, error } = await supabase
      .from('cards')
      .select('*, sets!inner(id, name, series, language)')
      .eq('number', num)
      .eq('sets.language', langFilter)
      .limit(topK * 3);

    if (!error && data && data.length > 0) {
      allRows = data;
      break; // Found matches, stop trying variants
    }
  }

  if (allRows.length === 0) return [];

  const results = allRows.map(row => ({
    id: row.id as string,
    name: row.name as string,
    name_en: (row.name_en as string) || undefined,
    number: row.number as string,
    set_id: row.set_id as string,
    set_name: (row.sets as { name: string })?.name ?? '',
    rarity: row.rarity as string,
    image_small: row.image_small as string,
    image_large: row.image_large as string,
    supertype: row.supertype as string,
    subtypes: row.subtypes as string[],
    hp: row.hp as string,
    artist: (row.artist as string) ?? '',
    confidence: 0.85,
    method: 'ocr' as const,
  }));

  // Use name hint to rank — if name matches, boost confidence significantly
  if (nameHint && nameHint.length >= 2) {
    const hint = nameHint.toLowerCase();
    for (const r of results) {
      const name = r.name.toLowerCase();
      const nameEn = (r.name_en ?? '').toLowerCase();
      if (name.includes(hint) || hint.includes(name) || nameEn.includes(hint) || hint.includes(nameEn)) {
        r.confidence = 0.95;
      }
    }
  }

  results.sort((a, b) => b.confidence - a.confidence);
  return results.slice(0, topK);
}

/** Search cards by fuzzy name match. */
async function searchByName(
  nameQuery: string,
  topK: number,
  lang: ScanLanguage,
): Promise<ScanMatch[]> {
  const { data, error } = await supabase.rpc('search_cards_fuzzy', {
    query: nameQuery,
    result_limit: topK * 3,
  });

  if (error || !data) return [];

  const filtered = data.filter(row => {
    if (lang === 'ja') return row.set_id.endsWith('-ja');
    return !row.set_id.endsWith('-ja') && !row.set_id.endsWith('-th');
  });

  return filtered.slice(0, topK).map(row => ({
    id: row.id,
    name: row.name,
    name_en: row.name_en || undefined,
    number: row.number,
    set_id: row.set_id,
    set_name: '',
    rarity: row.rarity,
    image_small: row.image_small,
    image_large: row.image_large,
    supertype: row.supertype,
    subtypes: row.subtypes,
    hp: row.hp,
    artist: row.artist ?? '',
    confidence: Math.max(0, Math.min(0.99, row.similarity)),
    method: 'ocr' as const,
  }));
}

// ── Optional visual embedding boost ──────────────────────────────────────────

async function tryVisualMatch(
  imageFile: File | Blob,
  topK: number,
  lang: ScanLanguage,
): Promise<ScanMatch[]> {
  try {
    const formData = new FormData();
    formData.append('file', imageFile);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    const res = await fetch(`${HF_SPACE_URL}/embed`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) return [];
    const { embedding } = await res.json();
    if (!embedding) return [];

    const embeddingStr = '[' + embedding.join(',') + ']';
    const { data, error } = await supabase.rpc('match_card', {
      query_embedding: embeddingStr,
      match_count: topK * 3,
    });

    if (error || !data) return [];

    const allMatches: ScanMatch[] = data.map((row) => ({
      id: row.id,
      name: row.name,
      number: row.number,
      set_id: row.set_id,
      set_name: '',
      rarity: row.rarity,
      image_small: row.image_small,
      image_large: row.image_large,
      supertype: row.supertype,
      subtypes: row.subtypes,
      hp: row.hp,
      artist: row.artist ?? '',
      confidence: Math.max(0, Math.min(0.99, row.similarity)),
      method: 'visual' as const,
    }));

    if (lang === 'en') {
      return allMatches.filter(m => !m.set_id.endsWith('-ja') && !m.set_id.endsWith('-th'));
    }
    return allMatches.filter(m => m.set_id.endsWith(`-${lang}`));
  } catch {
    return [];
  }
}

/** Merge OCR and visual results — if both agree on a card, boost confidence. */
function mergeResults(ocrMatches: ScanMatch[], visualMatches: ScanMatch[], topK: number): ScanMatch[] {
  const merged = new Map<string, ScanMatch>();

  for (const m of ocrMatches) {
    merged.set(m.id, { ...m });
  }

  for (const m of visualMatches) {
    const existing = merged.get(m.id);
    if (existing) {
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

// ── Main scan ────────────────────────────────────────────────────────────────

/**
 * Scan a card image:
 *   1. Crop top 25% → multi-pass OCR name, crop bottom 12% → multi-pass OCR number
 *   2. Search by number (most accurate) or fuzzy name search
 *   3. Optionally boost with visual embedding if cloud model is available
 */
export async function supabaseScan(
  imageFile: File | Blob,
  topK = 5,
  lang: ScanLanguage = 'en',
): Promise<ScanResult> {
  // 1. Start visual matching immediately (runs in parallel with OCR)
  const visualPromise = tryVisualMatch(imageFile, topK, lang).catch(() => [] as ScanMatch[]);

  // 2. Multi-pass OCR on name and number regions in parallel
  let nameResult: OcrResult = { text: '', confidence: 0 };
  let numberResult: OcrResult = { text: '', confidence: 0 };

  try {
    [nameResult, numberResult] = await Promise.all([
      ocrMultiPass(imageFile, 0, 0.25, 2, NAME_PROFILES, lang),
      ocrMultiPass(imageFile, 0.85, 1, 3, NUMBER_PROFILES, lang),
    ]);
  } catch (err) {
    console.warn('[supabaseScan] Crop/OCR failed:', err);
  }

  const nameText = nameResult.text;
  const numberText = numberResult.text;
  const ocrText = numberText ? `${nameText}\n[bottom] ${numberText}` : nameText;

  const cardNumber = extractCardNumber(numberText)
    || extractCardNumber(nameText)
    || extractCardNumber(nameText + ' ' + numberText);
  const nameQuery = extractNameQuery(nameText, lang);

  // 3. Search by number first (most reliable), then by name
  let ocrMatches: ScanMatch[] = [];

  if (cardNumber) {
    ocrMatches = await searchByNumber(cardNumber, nameQuery, topK, lang);
  }

  if (ocrMatches.length === 0 && nameQuery.length >= 1) {
    ocrMatches = await searchByName(nameQuery, topK, lang);
  }

  // Retry with wider bottom crop (20%) if nothing found yet
  if (ocrMatches.length === 0) {
    try {
      const wideBottom = await ocrMultiPass(imageFile, 0.80, 1, 3, NUMBER_PROFILES, lang);
      const wideNumber = extractCardNumber(wideBottom.text);
      if (wideNumber) {
        ocrMatches = await searchByNumber(wideNumber, nameQuery, topK, lang);
      }
    } catch { /* ignore */ }
  }

  // Last resort: OCR the full image (handles desktop uploads without card guide crop)
  if (ocrMatches.length === 0) {
    try {
      const fullResult = await ocrMultiPass(imageFile, 0, 1, 1, NAME_PROFILES.slice(0, 1), lang);
      const fullNumber = extractCardNumber(fullResult.text);
      const fullName = extractNameQuery(fullResult.text, lang);
      if (fullNumber) {
        ocrMatches = await searchByNumber(fullNumber, fullName, topK, lang);
      }
      if (ocrMatches.length === 0 && fullName.length >= 2) {
        ocrMatches = await searchByName(fullName, topK, lang);
      }
    } catch { /* ignore */ }
  }

  // 4. Await visual results and merge
  const visualMatches = await visualPromise;

  const matches = visualMatches.length > 0
    ? mergeResults(ocrMatches, visualMatches, topK)
    : ocrMatches;

  // Enrich Japanese matches with English names
  if (lang === 'ja' && matches.length > 0) {
    const jaIds = matches.filter(m => !m.name_en).map(m => m.id);
    if (jaIds.length > 0) {
      const { data } = await supabase
        .from('cards')
        .select('id, name_en')
        .in('id', jaIds)
        .neq('name_en', '');
      if (data) {
        const nameMap = new Map(data.map(r => [r.id, r.name_en]));
        for (const m of matches) {
          const en = nameMap.get(m.id);
          if (en) m.name_en = en;
        }
      }
    }
  }

  const methodUsed = visualMatches.length > 0 && ocrMatches.length > 0
    ? 'combined'
    : visualMatches.length > 0 ? 'visual' : ocrMatches.length > 0 ? 'ocr' : 'none';

  const cropNameUrl = nameResult.cropBlob ? URL.createObjectURL(nameResult.cropBlob) : undefined;
  const cropNumberUrl = numberResult.cropBlob ? URL.createObjectURL(numberResult.cropBlob) : undefined;

  return {
    matches,
    ocr_text: ocrText,
    method_used: methodUsed as ScanResult['method_used'],
    visual_index_size: visualMatches.length,
    catalog_size: 0,
    cropNameUrl,
    cropNumberUrl,
  };
}
