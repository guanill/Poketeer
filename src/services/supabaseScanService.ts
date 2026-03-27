/**
 * Supabase-backed card scanning.
 *
 * Pipeline:
 *   1. Crop top 25% of card image → OCR the name
 *   2. Crop bottom 12% → OCR the card number
 *   3. Search by number first (most accurate), then fuzzy name search
 *   4. Optional: if cloud embedding model is up, boost/merge with visual matches
 */

import { supabase } from '../lib/supabase';
import type { ScanMatch, ScanResult, ScanLanguage } from './cardScanService';

// HF Space URL for optional visual embedding boost
const HF_SPACE_URL = 'https://agm3000-poketeer-card-embedder.hf.space';

const EMPTY_RESULT: ScanResult = {
  matches: [],
  ocr_text: '',
  method_used: 'none',
  visual_index_size: 0,
  catalog_size: 0,
};

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

/** Crop the top 25% of the card (where the name lives). */
function cropNameRegion(imageFile: File | Blob): Promise<Blob> {
  return cropRegion(imageFile, 0, 0.25, 'grayscale(1) contrast(1.8) brightness(1.1)', 2);
}

/** Crop the bottom 12% of the card (where the card number lives). */
function cropNumberRegion(imageFile: File | Blob): Promise<Blob> {
  return cropRegion(imageFile, 0.88, 1, 'grayscale(1) contrast(2.5) brightness(1.15)', 3);
}

// ── OCR ──────────────────────────────────────────────────────────────────────

async function ocrBlob(blob: Blob, lang: ScanLanguage): Promise<string> {
  const { createWorker } = await import('tesseract.js');
  const tessLang = lang === 'ja' ? 'jpn+eng' : 'eng';
  const worker = await createWorker(tessLang);
  const { data } = await worker.recognize(blob);
  await worker.terminate();
  return data.text.trim();
}

// ── Text extraction helpers ──────────────────────────────────────────────────

/** Extract a card number like "4/102", "025/172", "SWSH025" from OCR text. */
function extractCardNumber(text: string): string | null {
  const slashMatch = text.match(/([A-Z]{0,4}\d{1,4})\s*[/\\|]\s*[A-Z0-9]+/i);
  if (slashMatch) return slashMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();

  const promoMatch = text.match(/\b([A-Z]{2,4}\d{3,4})\b/i);
  if (promoMatch) return promoMatch[1].replace(/^0+(?=\d)/, '').toLowerCase();

  const bareNum = text.match(/\b(\d{1,4})\s*[/\\|]/);
  if (bareNum) return bareNum[1].replace(/^0+(?=\d)/, '');

  return null;
}

/** Extract the card name from OCR text, handling both EN and JA. */
function extractNameQuery(text: string, lang: ScanLanguage): string {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  if (lines.length === 0) return '';

  if (lang === 'ja') {
    // Keep CJK + katakana + hiragana + Latin chars, drop noise
    for (const line of lines.slice(0, 4)) {
      const clean = line
        .replace(/[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEFa-zA-Z\s'.\-]/g, '')
        .trim();
      if (clean.length >= 1) return clean;
    }
    return lines[0];
  }

  // English: take first meaningful line, strip non-alpha noise
  for (const line of lines.slice(0, 4)) {
    const clean = line.replace(/[^a-zA-Z\u00C0-\u024F\s'.\-]/g, ' ').replace(/\s+/g, ' ').trim();
    if (clean.length >= 2) return clean;
  }
  return lines[0];
}

// ── Supabase search helpers ──────────────────────────────────────────────────

/** Search cards by number + optional name hint. */
async function searchByNumber(
  cardNumber: string,
  nameHint: string,
  topK: number,
  lang: ScanLanguage,
): Promise<ScanMatch[]> {
  // Search for the number across all cards
  let query = supabase
    .from('cards')
    .select('*, sets!inner(id, name, series, language)')
    .eq('number', cardNumber);

  // Filter by language
  if (lang === 'ja') {
    query = query.eq('sets.language', 'ja');
  } else {
    query = query.eq('sets.language', 'en');
  }

  const { data, error } = await query.limit(topK * 2);
  if (error || !data || data.length === 0) return [];

  // If we have a name hint, sort by similarity to it
  const results = data.map(row => ({
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
    confidence: 0.85, // Number match = high base confidence
    method: 'ocr' as const,
  }));

  // Boost cards whose name matches the hint
  if (nameHint) {
    const hint = nameHint.toLowerCase();
    for (const r of results) {
      const name = r.name.toLowerCase();
      const nameEn = (r.name_en ?? '').toLowerCase();
      if (name.includes(hint) || hint.includes(name) || nameEn.includes(hint)) {
        r.confidence = 0.95;
      }
    }
    results.sort((a, b) => b.confidence - a.confidence);
  }

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

  // Filter by language
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

    // Filter by language
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
 *   1. Crop top 25% → OCR name, crop bottom 12% → OCR number
 *   2. Search by number (most accurate) or fuzzy name search
 *   3. Optionally boost with visual embedding if cloud model is available
 */
export async function supabaseScan(
  imageFile: File | Blob,
  topK = 5,
  lang: ScanLanguage = 'en',
): Promise<ScanResult> {
  // 1. Crop and OCR name + number regions in parallel
  let nameText = '';
  let numberText = '';

  try {
    const [nameCrop, numberCrop] = await Promise.all([
      cropNameRegion(imageFile),
      cropNumberRegion(imageFile),
    ]);

    [nameText, numberText] = await Promise.all([
      ocrBlob(nameCrop, lang),
      ocrBlob(numberCrop, lang),
    ]);
  } catch (err) {
    console.warn('[supabaseScan] Crop/OCR failed:', err);
  }

  const ocrText = numberText ? `${nameText}\n[bottom] ${numberText}` : nameText;
  const cardNumber = extractCardNumber(numberText) || extractCardNumber(nameText);
  const nameQuery = extractNameQuery(nameText, lang);

  // 2. Search by number first (most reliable), then by name
  let ocrMatches: ScanMatch[] = [];

  if (cardNumber) {
    ocrMatches = await searchByNumber(cardNumber, nameQuery, topK, lang);
  }

  if (ocrMatches.length === 0 && nameQuery.length >= 1) {
    ocrMatches = await searchByName(nameQuery, topK, lang);
  }

  // 3. Try visual matching in parallel (non-blocking — if it fails, we still have OCR)
  const visualMatches = await tryVisualMatch(imageFile, topK, lang).catch(() => [] as ScanMatch[]);

  // 4. Merge results
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

  return {
    matches,
    ocr_text: ocrText,
    method_used: methodUsed as ScanResult['method_used'],
    visual_index_size: visualMatches.length,
    catalog_size: 0,
  };
}
