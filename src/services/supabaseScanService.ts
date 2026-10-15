/**
 * Supabase-backed card scanning.
 *
 * Pipeline:
 *   1. Send image to PaddleOCR HF Space → get card name, number, set code
 *   2. Fallback: client-side Tesseract.js multi-pass OCR
 *   3. Search by number and name independently, then rank by combined evidence
 *   4. Use visual similarity as corroborating evidence rather than a standalone answer
 */

import { supabase } from '../lib/supabase';
import type { ScanMatch, ScanResult, ScanLanguage } from './cardScanService';
import { mergeScanMatches, rankNumberMatches } from './scanRanking';

// HF Space URLs
const HF_SPACE_URL = 'https://agm3000-poketeer-card-embedder.hf.space';
const HF_OCR_URL = 'https://agm3000-poketeer-card-ocr.hf.space';

// ── PaddleOCR via HF Space ──────────────────────────────────────────────────

interface PaddleOcrResult {
  name: string;
  name_en?: string;
  number: string;
  set_code: string;
  detected_lang?: 'en' | 'ja' | 'th';
  all_text: Array<{ text: string; confidence: number; region: string; position: { y_center: number; x_center: number } }>;
}

function extractPaddleCardNumber(result: PaddleOcrResult): string | null {
  const footerText = (result.all_text ?? [])
    .filter(item => item.region === 'number' || item.position?.y_center >= 0.8)
    .sort((a, b) => a.position.y_center - b.position.y_center)
    .map(item => item.text)
    .join(' ');

  return extractCardNumber(footerText, true)
    || extractStructuredCardNumber(result.number);
}

function extractStructuredCardNumber(value: string): string | null {
  const normalized = value.trim().replace(/^0+(?=\d)/, '');
  return /^[A-Za-z]{1,4}\d{1,4}$/.test(normalized) || /^\d{1,4}$/.test(normalized)
    ? normalized
    : null;
}

// ── HF Space warm-up ────────────────────────────────────────────────────────

let _hfWarmupDone = false;

/** Ping the HF OCR Space so it wakes from sleep before the user scans. */
export function warmupHfSpace(): void {
  if (_hfWarmupDone) return;
  _hfWarmupDone = true;
  fetch(`${HF_OCR_URL}/health`, { method: 'GET' }).catch(() => {});
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
function extractCardNumber(text: string, allowFooterCode = false): string | null {
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

  if (allowFooterCode) {
    // Alphanumeric collector numbers (e.g. TG30, GG01, SWSH025) are printed
    // in the footer alongside the numeric "number/total" format.
    const collectorCode = raw.match(/\b([A-Z]{1,4}\d{1,4})\b/i);
    if (collectorCode) return collectorCode[1].toLowerCase();

    // Only accept a bare number when OCR was run on the isolated card-number crop.
    const bareNumber = raw.match(/^\s*[#№]?\s*(\d{1,4})\s*$/m);
    if (bareNumber) return bareNumber[1].replace(/^0+(?=\d)/, '');
  }

  return null;
}

/** Extract a set code/abbreviation from OCR text (e.g. "SV6", "S12a", "MEW"). */
function extractSetHint(text: string, cardNumber = ''): string {
  const patterns = /\b(?:SV\d{1,2}(?:PT\d)?|S\d{1,2}[A-Z]{0,2}|SM\d{1,2}[A-Z+]{0,2}|XY\d{1,2}[A-Z]{0,2}|BW\d{1,2}[A-Z]{0,2}|SWSH\d{0,3}|MEW|SVP|SMP\d?|SC\d[A-Z]?|MA\d|PCG\d{1,2}|ADV\d{1,2}|CP\d{1,2}|L\d[A-Z]?)\b/ig;
  const numberKey = cardNumber.toUpperCase();
  return [...text.matchAll(patterns)]
    .map(match => match[0])
    .find(candidate => candidate.toUpperCase() !== numberKey) ?? '';
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

// ── OCR name cleaning ───────────────────────────────────────────────────────

/** Pokemon suffix patterns to strip for base-name fallback. */
const POKEMON_SUFFIXES_RE = /\s*[-\s]?\b(ex|EX|gx|GX|v|V|vstar|VSTAR|vmax|VMAX|v-?union|V-?UNION|break|BREAK|lv\.\s*x|LV\.\s*X|mega|MEGA|δ)\s*$/i;

/** Junk that OCR may include in the name text. */
const JUNK_IN_NAME_RE = /\b(HP\s*\d+|\d+\s*HP|Basic|Stage\s*\d|たね|1進化|2進化|item|trainer|supporter|energy)\b/gi;

/** Clean an OCR name: strip suffixes, junk, extra whitespace, stray punctuation. */
function cleanOcrName(raw: string): { cleaned: string; baseName: string } {
  // Strip stray OCR punctuation (quotes, brackets, pipes)
  let cleaned = raw.replace(/[""''「」【】\[\](){}|~`]/g, '').trim();
  // Strip obvious junk
  cleaned = cleaned.replace(JUNK_IN_NAME_RE, '').replace(/\s{2,}/g, ' ').trim();
  // Strip trailing numbers (OCR sometimes merges HP/number into name)
  cleaned = cleaned.replace(/\s+\d{2,}$/, '').trim();
  // Strip leading/trailing punctuation remnants
  cleaned = cleaned.replace(/^[.,;:!?\-–—]+|[.,;:!?\-–—]+$/g, '').trim();

  // Base name = without Pokemon suffix (e.g. "Charizard" from "Charizard ex")
  const baseName = cleaned.replace(POKEMON_SUFFIXES_RE, '').trim();

  return { cleaned, baseName: baseName !== cleaned ? baseName : '' };
}

// ── OCR metadata extraction ─────────────────────────────────────────────────

/** Extract HP value from PaddleOCR all_text (e.g. "HP 120" → "120"). */
function extractHpHint(allText: PaddleOcrResult['all_text']): string {
  for (const t of allText) {
    const m = t.text.match(/\b(?:HP|hp)\s*(\d{2,3})\b/) || t.text.match(/\b(\d{2,3})\s*(?:HP|hp)\b/);
    if (m) return m[1];
  }
  return '';
}

/** Detect supertype from OCR text: "Pokémon", "Trainer", or "Energy". */
function detectSupertype(allText: PaddleOcrResult['all_text']): string {
  const combined = allText.map(t => t.text).join(' ');
  // Trainer keywords (EN/JA/TH)
  if (/\b(Trainer|Supporter|Item|Stadium|Tool|トレーナーズ|サポート|グッズ|スタジアム|ผู้ฝึก|ไอเทม)\b/i.test(combined)) {
    return 'Trainer';
  }
  // Energy keywords
  if (/\b(Energy|エネルギー|พลังงาน)\b/i.test(combined)) {
    return 'Energy';
  }
  return ''; // Default: Pokémon (most common, don't filter)
}

/**
 * Generate OCR char-correction variants of a name for ilike queries.
 * E.g. "Charizand" → ["Charizand", "Charizard"] (d↔rd isn't a char swap,
 * but "0"↔"O", "1"↔"l"/"I", "5"↔"S" are common OCR confusions).
 */
function nameSearchVariants(name: string): string[] {
  const variants = new Set<string>([name]);
  // Common OCR char swaps (reverse of number corrections)
  const swaps: [RegExp, string][] = [
    [/0/g, 'O'], [/O/g, '0'],
    [/1/g, 'l'], [/l/g, '1'],
    [/5/g, 'S'], [/S/g, '5'],
    [/8/g, 'B'], [/B/g, '8'],
    [/rn/g, 'm'], [/m/g, 'rn'], // OCR often reads "m" as "rn"
  ];
  for (const [pattern, replacement] of swaps) {
    const variant = name.replace(pattern, replacement);
    if (variant !== name && variant.length >= 2) variants.add(variant);
  }
  return [...variants];
}

// ── Fuzzy string matching ────────────────────────────────────────────────────

// ── Supabase search helpers ──────────────────────────────────────────────────

/** Convert DB rows to ScanMatch objects. */
function rowsToMatches(rows: Array<Record<string, unknown>>): ScanMatch[] {
  return rows.map(row => ({
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
}

function normalizeCardNumber(value: string): string {
  const normalized = value.replace(/\s+/g, '').toUpperCase();
  return /^\d+$/.test(normalized) ? normalized.replace(/^0+(?=\d)/, '') : normalized;
}

/** Build exact and numeric-neighbor variants without stripping promo prefixes. */
function buildNumberVariants(cardNumber: string): { exact: string[]; nearby: string[] } {
  const exact = new Set<string>([cardNumber, cardNumber.toUpperCase()]);
  const numOnly = /^\d+$/.test(cardNumber) ? cardNumber : '';
  if (numOnly.length > 0) {
    exact.add(numOnly);
    exact.add(numOnly.padStart(3, '0'));
    exact.add(numOnly.padStart(2, '0'));
  }

  const nearby = new Set<string>();
  const n = parseInt(numOnly, 10);
  if (!isNaN(n)) {
    for (const offset of [-1, 1]) {
      const adj = n + offset;
      if (adj > 0) {
        nearby.add(String(adj));
        nearby.add(String(adj).padStart(3, '0'));
      }
    }
  }
  for (const e of exact) {
    for (const candidate of nearby) {
      if (normalizeCardNumber(candidate) === normalizeCardNumber(e)) nearby.delete(candidate);
    }
  }

  return { exact: [...exact], nearby: [...nearby] };
}

/** Try to resolve set hint to actual set_id suffixes for precise filtering. */
function resolveSetIds(setHint: string, lang: ScanLanguage): string[] {
  if (!setHint || setHint.length < 2) return [];
  const hint = setHint.toLowerCase();
  const langSuffix = `-${lang}`;
  // Common patterns: "sv6" → "sv6-en", "s12a" → "s12a-ja"
  return [`${hint}${langSuffix}`];
}

/** Search exact and nearby numbers, then rank candidates against all OCR evidence. */
async function searchByNumber(
  cardNumber: string,
  nameHint: string,
  topK: number,
  lang: ScanLanguage,
  setHint = '',
  hpHint = '',
  supertypeHint = '',
): Promise<ScanMatch[]> {
  const { exact, nearby } = buildNumberVariants(cardNumber);
  const langFilter = lang === 'ja' ? 'ja' : lang === 'th' ? 'th' : 'en';
  const { cleaned: cleanedName, baseName } = cleanOcrName(nameHint);
  const nameVariants = [cleanedName, ...(baseName ? [baseName] : [])].filter(n => n.length >= 2);
  const setIds = resolveSetIds(setHint, lang);
  const selectCards = () => supabase
    .from('cards')
    .select('*, sets!inner(id, name, series, language)');

  const exactQueries = [
    selectCards().in('number', exact).eq('sets.language', langFilter).limit(200),
    ...(setIds.length > 0
      ? [selectCards().in('set_id', setIds).in('number', exact).limit(20)]
      : []),
  ];
  const nearbyQueries = nearby.length > 0 && nameVariants.length > 0
    ? [...new Set(nameVariants.flatMap(nameSearchVariants))].map(term => {
        const orFilter = lang === 'en'
          ? `name.ilike.%${term}%`
          : `name.ilike.%${term}%,name_en.ilike.%${term}%`;
        return selectCards()
          .in('number', nearby)
          .or(orFilter)
          .eq('sets.language', langFilter)
          .limit(50);
      })
    : [];
  const [exactResponses, nearbyResponses] = await Promise.all([
    Promise.all(exactQueries),
    Promise.all(nearbyQueries),
  ]);
  const exactRows = exactResponses.flatMap(({ data, error }) => !error && data ? data : []);
  const nearbyRows = nearbyResponses.flatMap(({ data, error }) => !error && data ? data : []);
  const candidates = [...rowsToMatches(exactRows), ...rowsToMatches(nearbyRows)];

  if (candidates.length === 0) return [];

  const unique = new Map<string, ScanMatch>();
  for (const candidate of candidates) unique.set(candidate.id, candidate);

  const ranked = rankNumberMatches([...unique.values()], {
    cardNumber,
    setHint,
    nameHints: nameVariants,
    hpHint,
    supertypeHint,
    nearbyNumbers: nearby,
  });

  return ranked.slice(0, topK);
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

// ── Main scan ────────────────────────────────────────────────────────────────

/**
 * Scan a card image:
 *   1. Try PaddleOCR (HF Space) — best accuracy
 *   2. Fallback: client-side Tesseract.js multi-pass OCR
 *   3. Search by number and name independently and rank all candidate evidence
 *   4. Use visual similarity as corroborating evidence when available
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
  let hpHint = '';
  let supertypeHint = '';
  let ocrText = '';
  let usedPaddle = false;
  let effectiveLang = lang;  // May be overridden by auto-detection

  const paddleResult = await tryPaddleOcr(imageFile, 'auto');

  if (paddleResult && (paddleResult.name || paddleResult.number)) {
    usedPaddle = true;
    cardNumber = extractPaddleCardNumber(paddleResult);
    nameQuery = paddleResult.name;
    setHint = normalizeCardNumber(paddleResult.set_code) === normalizeCardNumber(cardNumber ?? '')
      ? ''
      : paddleResult.set_code;

    // Extract extra signals from all_text
    if (paddleResult.all_text) {
      hpHint = extractHpHint(paddleResult.all_text);
      supertypeHint = detectSupertype(paddleResult.all_text);
    }

    // Use auto-detected language for DB search
    if (paddleResult.detected_lang) {
      effectiveLang = paddleResult.detected_lang;
    }

    // For non-EN cards: if OCR found an English name (small text on card),
    // use it as the search name — it matches the `name_en` DB field and is
    // more reliable than the garbled native-script name from the EN engine.
    if (effectiveLang !== 'en' && paddleResult.name_en && paddleResult.name_en.length >= 2) {
      // If the main name is non-Latin (Thai/Japanese), prefer the English name for search
      const hasNonLatin = /[^\x00-\x7F]/.test(nameQuery);
      if (hasNonLatin || nameQuery.length < 2) {
        console.log('[scan] Using name_en for search:', paddleResult.name_en, '(original:', nameQuery, ')');
        nameQuery = paddleResult.name_en;
      }
    }

    ocrText = `[PaddleOCR] name: ${paddleResult.name} | number: ${cardNumber ?? ''} | set: ${paddleResult.set_code} | lang: ${effectiveLang}`;
    if (paddleResult.name_en) ocrText += ` | name_en: ${paddleResult.name_en}`;
    if (hpHint) ocrText += ` | hp: ${hpHint}`;
    if (supertypeHint) ocrText += ` | type: ${supertypeHint}`;

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

    cardNumber = extractCardNumber(numberText, true)
      || extractCardNumber(nameText)
      || extractCardNumber(nameText + ' ' + numberText);
    nameQuery = extractNameQuery(nameText, lang);
    setHint = extractSetHint(numberText, cardNumber ?? '');

    console.log('[scan] Tesseract name:', JSON.stringify(nameText), `(conf: ${nameResult.confidence})`);
    console.log('[scan] Tesseract number:', JSON.stringify(numberText), `(conf: ${numberResult.confidence})`);
  }

  console.log('[scan] extracted → number:', cardNumber, '| name:', nameQuery, '| set:', setHint);

  // Clean OCR name before searching
  const { cleaned: cleanedNameQuery, baseName: baseNameQuery } = cleanOcrName(nameQuery);

  // Search by number and name independently: an OCR number can be wrong even
  // when the name is readable, so neither signal should hide the other.
  const nameQueries = [...new Set([cleanedNameQuery, baseNameQuery].filter(
    name => effectiveLang === 'ja' ? name.length >= 1 : name.length >= 2,
  ))];
  const [numberMatches, ...nameResultGroups] = await Promise.all([
    cardNumber
      ? searchByNumber(cardNumber, cleanedNameQuery, topK * 3, effectiveLang, setHint, hpHint, supertypeHint)
      : Promise.resolve([] as ScanMatch[]),
    ...nameQueries
      .map(name => searchByName(name, topK * 3, effectiveLang)),
  ]);
  const candidateMap = new Map<string, ScanMatch>();
  for (const match of [...numberMatches, ...nameResultGroups.flat()]) {
    const previous = candidateMap.get(match.id);
    if (!previous || previous.confidence < match.confidence) candidateMap.set(match.id, match);
  }
  const numberVariants = cardNumber ? buildNumberVariants(cardNumber) : { nearby: [] as string[] };
  let ocrMatches = rankNumberMatches([...candidateMap.values()], {
    cardNumber: cardNumber ?? '',
    setHint,
    nameHints: nameQueries,
    hpHint,
    supertypeHint,
    nearbyNumbers: numberVariants.nearby,
  }).slice(0, topK);

  // If auto-detected language found nothing, retry with other languages
  if (ocrMatches.length === 0 && usedPaddle && cardNumber) {
    const otherLangs: ScanLanguage[] = (['en', 'ja', 'th'] as const).filter(l => l !== effectiveLang);
    for (const tryLang of otherLangs) {
      ocrMatches = await searchByNumber(cardNumber, cleanedNameQuery, topK, tryLang, setHint, hpHint, supertypeHint);
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
      const wideNumber = extractCardNumber(wideBottom.text, true);
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

  const matches = mergeScanMatches(ocrMatches, visualMatches, topK);

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
