/**
 * Supabase-backed card scanning.
 *
 * Pipeline:
 *   1. Send image to PaddleOCR HF Space → get card name, number, set code
 *   2. Fallback: client-side Tesseract.js multi-pass OCR
 *   3. Search by number first (most accurate), then fuzzy name search
 *   4. Optional: if cloud embedding model is up, boost/merge with visual matches
 */

import { supabase } from '../lib/supabase';
import type { ScanMatch, ScanResult, ScanLanguage } from './cardScanService';

// HF Space URLs
const HF_SPACE_URL = 'https://agm3000-poketeer-card-embedder.hf.space';
const HF_OCR_URL = 'https://agm3000-poketeer-card-ocr.hf.space';

// ── PaddleOCR via HF Space ──────────────────────────────────────────────────

interface PaddleOcrResult {
  name: string;
  number: string;
  set_code: string;
  detected_lang?: 'en' | 'ja' | 'th';
  all_text: Array<{ text: string; confidence: number; region: string; position: { y_center: number; x_center: number } }>;
}

async function tryPaddleOcr(imageFile: File | Blob, lang: ScanLanguage | 'auto' = 'auto'): Promise<PaddleOcrResult | null> {
  try {
    const formData = new FormData();
    formData.append('file', imageFile);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const res = await fetch(`${HF_OCR_URL}/ocr?lang=${lang}`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

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
  { label: 'sharpen',       filter: 'grayscale(1) contrast(2.2) brightness(1.05) saturate(0)' },
];

const NUMBER_PROFILES = [
  { label: 'balanced',      filter: 'grayscale(1) contrast(2.5) brightness(1.15)' },
  { label: 'high-contrast', filter: 'grayscale(1) contrast(3.5) brightness(1.3)' },
  { label: 'inverted',      filter: 'grayscale(1) contrast(2.0) brightness(1.4) invert(1)' },
  { label: 'sharpen',       filter: 'grayscale(1) contrast(3.0) brightness(1.0) saturate(0)' },
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

/** Preload the Tesseract worker for a given language so the first scan is fast. */
export function preloadWorker(lang: ScanLanguage): void {
  getWorker(lang).catch(() => {});
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
  // First try matching on the raw text (before aggressive substitutions)
  const raw = text.replace(/[—–-]+/g, '/').replace(/\s+/g, ' ');

  // Pattern A: "4/102", "025/172", "TG30/TG30"
  const slashRaw = raw.match(/([A-Za-z]{0,4}\d{1,4})\s*[/\\|]\s*[A-Za-z0-9]+/);
  if (slashRaw) return slashRaw[1].replace(/^0+(?=\d)/, '').toLowerCase();

  // Pattern B: bare number near a slash
  const bareRaw = raw.match(/\b(\d{1,4})\s*[/\\|]/);
  if (bareRaw) return bareRaw[1].replace(/^0+(?=\d)/, '');

  // Now try with OCR misread corrections (only within digit-heavy segments)
  const cleaned = raw
    .replace(/(?<=\d)[oO]|[oO](?=\d)/g, '0')  // O→0 only next to digits
    .replace(/(?<=\d)[lI]|[lI](?=\d)/g, '1')   // l/I→1 only next to digits
    .replace(/(?<=\d)[sS]|[sS](?=\d)/g, '5');  // S→5 only next to digits

  const slashFixed = cleaned.match(/([A-Za-z]{0,4}\d{1,4})\s*[/\\|]\s*[A-Za-z0-9]+/);
  if (slashFixed) return slashFixed[1].replace(/^0+(?=\d)/, '').toLowerCase();

  // Pattern C: standalone promo codes like "SWSH025"
  const promoMatch = raw.match(/\b([A-Z]{2,4}\d{3,4})\b/i);
  if (promoMatch) return promoMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();

  // Pattern D: just a number (last resort)
  const anyNum = raw.match(/\b(\d{1,4})\b/);
  if (anyNum && anyNum[1].length >= 1) return anyNum[1].replace(/^0+(?=\d)/, '');

  return null;
}

/** Extract a set code/abbreviation from OCR text (e.g. "SV6", "S12a", "MEW"). */
function extractSetHint(text: string): string {
  // Common patterns: "SV6", "S12a", "SM12", "MEW", "sv6pt5" etc.
  const m = text.match(/\b([A-Za-z]{1,4}\d{1,3}[a-z]{0,3})\b/);
  return m ? m[1] : '';
}

/** Lines that are card metadata, not the card name. */
const JUNK_NAME_RE = /^(stage\s*[0-9]|basic|mega|break|v-?star|v-?max|v-?union|gx|ex|lv\.\s*x|restored|legend|item|trainer|supporter|stadium|energy|tool|たね|たねポケモン|1進化|2進化|進化|トレーナーズ|サポート|グッズ|スタジアム|エネルギー|ポケモンのどうぐ|ポケモン[VＶ]|BREAK|メガシンカ|M進化)/i;

/** Extract the card name from OCR text, handling both EN and JA. */
function extractNameQuery(text: string, lang: ScanLanguage): string {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  if (lines.length === 0) return '';

  if (lang === 'ja') {
    for (const line of lines.slice(0, 6)) {
      const clean = line
        .replace(/[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEFa-zA-Z\s'.\-]/g, '')
        .trim();
      if (clean.length >= 1 && !JUNK_NAME_RE.test(clean)) return clean;
    }
    return lines[0];
  }

  for (const line of lines.slice(0, 6)) {
    const clean = line.replace(/[^a-zA-Z\u00C0-\u024F\s'.\-]/g, ' ').replace(/\s+/g, ' ').trim();
    if (clean.length >= 2 && !JUNK_NAME_RE.test(clean)) return clean;
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
  setHint = '',
): Promise<ScanMatch[]> {
  // Try the number as-is + zero-padded to 3 digits (e.g. "5" → "005", "25" → "025")
  const variants = new Set<string>([cardNumber]);
  const numOnly = cardNumber.replace(/\D/g, '');
  if (numOnly.length > 0) {
    variants.add(numOnly);
    variants.add(numOnly.padStart(3, '0'));
    variants.add(numOnly.padStart(2, '0'));
  }

  // Map language to DB filter — TH cards are stored with language 'th'
  const langFilter = lang === 'ja' ? 'ja' : lang === 'th' ? 'th' : 'en';
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
      break;
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

  // Use name hint to rank — name match is the strongest signal
  if (nameHint && nameHint.length >= 2) {
    const hint = nameHint.toLowerCase().trim();
    for (const r of results) {
      const name = r.name.toLowerCase();
      const nameEn = (r.name_en ?? '').toLowerCase();

      // Exact match
      if (name === hint || nameEn === hint) {
        r.confidence = 0.99;
      }
      // Substring match (OCR read "Ferroseed" and card name contains it or vice versa)
      else if (name.includes(hint) || hint.includes(name) || nameEn.includes(hint) || hint.includes(nameEn)) {
        r.confidence = 0.95;
      }
      // No name match at all — penalize heavily so matching names always win
      else {
        r.confidence = 0.30;
      }
    }
  }

  // Use set hint to disambiguate — match against set_id code (most reliable)
  if (setHint && setHint.length >= 2) {
    const hint = setHint.toLowerCase();
    for (const r of results) {
      const setCode = r.set_id.replace(/-(?:en|ja|th)$/, '').toLowerCase();
      if (setCode === hint || setCode.startsWith(hint) || hint.startsWith(setCode)) {
        r.confidence = Math.min(0.99, r.confidence + 0.10);
      } else {
        const sname = r.set_name.toLowerCase();
        if (sname.includes(hint) || hint.includes(sname)) {
          r.confidence = Math.min(0.99, r.confidence + 0.04);
        }
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
    if (lang === 'th') return row.set_id.endsWith('-th');
    return !row.set_id.endsWith('-ja') && !row.set_id.endsWith('-th');
  });

  // Fetch set names for results
  const setIds = [...new Set(filtered.map(r => r.set_id))];
  const setNameMap = new Map<string, string>();
  if (setIds.length > 0) {
    const { data: sets } = await supabase.from('sets').select('id, name').in('id', setIds);
    if (sets) sets.forEach(s => setNameMap.set(s.id, s.name));
  }

  return filtered.slice(0, topK).map(row => ({
    id: row.id,
    name: row.name,
    name_en: row.name_en || undefined,
    number: row.number,
    set_id: row.set_id,
    set_name: setNameMap.get(row.set_id) ?? '',
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
 *   1. Try PaddleOCR (HF Space) — best accuracy
 *   2. Fallback: client-side Tesseract.js multi-pass OCR
 *   3. Search by number (most accurate) or fuzzy name search
 *   4. Optionally boost with visual embedding if cloud model is available
 */
export async function supabaseScan(
  imageFile: File | Blob,
  topK = 5,
  lang: ScanLanguage = 'en',
): Promise<ScanResult> {
  // 2. Try PaddleOCR first (cloud, high accuracy, auto-detect language)
  let cardNumber: string | null = null;
  let nameQuery = '';
  let setHint = '';
  let ocrText = '';
  let usedPaddle = false;
  let effectiveLang = lang;  // May be overridden by auto-detection

  const paddleResult = await tryPaddleOcr(imageFile, 'auto');

  if (paddleResult && (paddleResult.name || paddleResult.number)) {
    usedPaddle = true;
    cardNumber = paddleResult.number || null;
    nameQuery = paddleResult.name;
    setHint = paddleResult.set_code;

    // Use auto-detected language for DB search
    if (paddleResult.detected_lang) {
      effectiveLang = paddleResult.detected_lang;
    }

    ocrText = `[PaddleOCR] name: ${paddleResult.name} | number: ${paddleResult.number} | set: ${paddleResult.set_code} | lang: ${effectiveLang}`;

    console.log('[scan] PaddleOCR →', ocrText);
    if (paddleResult.all_text) {
      console.log('[scan] all text:', paddleResult.all_text.map(t => `${t.region}: "${t.text}" (${t.confidence})`).join(', '));
    }
  }

  // 1. Start visual matching (after we know the effective language)
  const visualPromise = tryVisualMatch(imageFile, topK, effectiveLang).catch(() => [] as ScanMatch[]);

  // 3. Fallback: client-side Tesseract.js if PaddleOCR failed
  if (!usedPaddle) {
    console.log('[scan] PaddleOCR unavailable, falling back to Tesseract.js');

    let nameResult: OcrResult = { text: '', confidence: 0 };
    let numberResult: OcrResult = { text: '', confidence: 0 };

    try {
      [nameResult, numberResult] = await Promise.all([
        ocrMultiPass(imageFile, 0.03, 0.18, 3, NAME_PROFILES, lang),
        ocrMultiPass(imageFile, 0.88, 0.97, 3, NUMBER_PROFILES, lang),
      ]);
    } catch (err) {
      console.warn('[supabaseScan] Crop/OCR failed:', err);
    }

    const nameText = nameResult.text;
    const numberText = numberResult.text;
    ocrText = numberText ? `${nameText}\n[bottom] ${numberText}` : nameText;

    cardNumber = extractCardNumber(numberText)
      || extractCardNumber(nameText)
      || extractCardNumber(nameText + ' ' + numberText);
    nameQuery = extractNameQuery(nameText, lang);
    setHint = extractSetHint(numberText);

    console.log('[scan] Tesseract name:', JSON.stringify(nameText), `(conf: ${nameResult.confidence})`);
    console.log('[scan] Tesseract number:', JSON.stringify(numberText), `(conf: ${numberResult.confidence})`);
  }

  console.log('[scan] extracted → number:', cardNumber, '| name:', nameQuery, '| set:', setHint);

  // 4. Search by number first (most reliable), then by name
  let ocrMatches: ScanMatch[] = [];

  if (cardNumber) {
    ocrMatches = await searchByNumber(cardNumber, nameQuery, topK, effectiveLang, setHint);
  }

  if (ocrMatches.length === 0 && nameQuery.length >= 1) {
    ocrMatches = await searchByName(nameQuery, topK, effectiveLang);
  }

  // If auto-detected language found nothing, retry with other languages
  if (ocrMatches.length === 0 && usedPaddle && cardNumber) {
    const otherLangs: ScanLanguage[] = (['en', 'ja', 'th'] as const).filter(l => l !== effectiveLang);
    for (const tryLang of otherLangs) {
      ocrMatches = await searchByNumber(cardNumber, nameQuery, topK, tryLang, setHint);
      if (ocrMatches.length > 0) {
        effectiveLang = tryLang;
        console.log('[scan] Retried with lang:', tryLang, '→ found', ocrMatches.length, 'matches');
        break;
      }
    }
  }

  // Retry with wider bottom crop (bottom 25%) if nothing found yet — Tesseract only
  if (ocrMatches.length === 0 && !usedPaddle) {
    try {
      const wideBottom = await ocrMultiPass(imageFile, 0.75, 1, 3, NUMBER_PROFILES, effectiveLang);
      const wideNumber = extractCardNumber(wideBottom.text);
      if (wideNumber) {
        ocrMatches = await searchByNumber(wideNumber, nameQuery, topK, effectiveLang);
      }
    } catch { /* ignore */ }
  }

  // Last resort: full-image OCR — Tesseract only
  if (ocrMatches.length === 0 && !usedPaddle) {
    try {
      const fullResult = await ocrMultiPass(imageFile, 0, 1, 1, NAME_PROFILES.slice(0, 1), effectiveLang);
      const fullNumber = extractCardNumber(fullResult.text);
      const fullName = extractNameQuery(fullResult.text, effectiveLang);
      if (fullNumber) {
        ocrMatches = await searchByNumber(fullNumber, fullName, topK, effectiveLang);
      }
      if (ocrMatches.length === 0 && fullName.length >= 2) {
        ocrMatches = await searchByName(fullName, topK, effectiveLang);
      }
    } catch { /* ignore */ }
  }

  // 4. Await visual results and merge
  const visualMatches = await visualPromise;

  const matches = visualMatches.length > 0
    ? mergeResults(ocrMatches, visualMatches, topK)
    : ocrMatches;

  // Enrich non-English matches with English names
  if (effectiveLang !== 'en' && matches.length > 0) {
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

  return {
    matches,
    ocr_text: ocrText,
    method_used: methodUsed as ScanResult['method_used'],
    visual_index_size: visualMatches.length,
    catalog_size: 0,
  };
}
