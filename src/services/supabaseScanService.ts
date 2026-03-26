/**
 * Supabase-backed card scanning.
 *
 * Pipeline:
 *   1. Try cloud: send image to HF Space → 512-D embedding → pgvector match
 *   2. Fallback: Tesseract OCR → fuzzy text search via Supabase RPC
 */

import { supabase } from '../lib/supabase';
import type { ScanMatch, ScanResult, ScanLanguage } from './cardScanService';

// HF Space URL — update after deploying
const HF_SPACE_URL = 'https://agm3000-poketeer-card-embedder.hf.space';

const EMPTY_RESULT: ScanResult = {
  matches: [],
  ocr_text: '',
  method_used: 'none',
  visual_index_size: 0,
  catalog_size: 0,
};

/**
 * Try to get embedding from the cloud model (HF Space).
 * Returns null if the service is down or unreachable.
 */
async function cloudEmbedding(imageFile: File | Blob): Promise<number[] | null> {
  try {
    const formData = new FormData();
    formData.append('file', imageFile);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000); // 30s timeout (cold start can be slow)

    const res = await fetch(`${HF_SPACE_URL}/embed`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) return null;
    const json = await res.json();
    return json.embedding as number[];
  } catch {
    console.warn('[supabaseScan] Cloud model unavailable, falling back to OCR');
    return null;
  }
}

/**
 * Fallback: use Tesseract.js OCR to read card name, then fuzzy search.
 */
async function ocrFallback(imageFile: File | Blob, topK: number, lang: ScanLanguage = 'en'): Promise<ScanResult> {
  try {
    const { createWorker } = await import('tesseract.js');
    // For Japanese, use jpn+eng to handle mixed text (numbers, Latin chars on JP cards)
    const tessLang = lang === 'ja' ? 'jpn+eng' : 'eng';
    const worker = await createWorker(tessLang);

    const buffer = await imageFile.arrayBuffer();
    const { data } = await worker.recognize(new Uint8Array(buffer));
    await worker.terminate();

    const ocrText = data.text.trim();
    if (!ocrText) return EMPTY_RESULT;

    // Extract likely card name (first non-empty line, cleaned up)
    const lines = ocrText.split('\n').map(l => l.trim()).filter(Boolean);
    const query = lines[0] ?? '';
    if (query.length < 2) return { ...EMPTY_RESULT, ocr_text: ocrText };

    // Fuzzy search via Supabase RPC
    const { data: results, error } = await supabase.rpc('search_cards_fuzzy', {
      query,
      result_limit: topK,
    });

    if (error || !results) return { ...EMPTY_RESULT, ocr_text: ocrText };

    const matches: ScanMatch[] = results.map((row) => ({
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
      method: 'ocr' as const,
    }));

    return {
      matches,
      ocr_text: ocrText,
      method_used: matches.length > 0 ? 'ocr' : 'none',
      visual_index_size: 0,
      catalog_size: 0,
    };
  } catch (err) {
    console.error('[supabaseScan] OCR fallback failed:', err);
    return EMPTY_RESULT;
  }
}

/**
 * Filter visual matches to only include cards in the requested language.
 * Cards belonging to sets with the language suffix (e.g., "-ja") are Japanese,
 * and cards without a suffix are English.
 */
function filterByLanguage(matches: ScanMatch[], lang: ScanLanguage): ScanMatch[] {
  if (lang === 'en') {
    // English cards don't have a language suffix in set_id
    return matches.filter(m => !m.set_id.endsWith('-ja') && !m.set_id.endsWith('-th'));
  }
  // Japanese cards have set_id ending with "-ja"
  return matches.filter(m => m.set_id.endsWith(`-${lang}`));
}

/**
 * Enrich Japanese card matches with their English names from the name_en column.
 */
async function enrichWithEnglishNames(matches: ScanMatch[]): Promise<void> {
  const jaIds = matches.filter(m => m.set_id.endsWith('-ja')).map(m => m.id);
  if (jaIds.length === 0) return;

  const { data } = await supabase
    .from('cards')
    .select('id, name_en')
    .in('id', jaIds)
    .neq('name_en', '');

  if (!data) return;

  const nameMap = new Map(data.map(r => [r.id, r.name_en]));
  for (const m of matches) {
    const en = nameMap.get(m.id);
    if (en) m.name_en = en;
  }
}

/**
 * Scan a card image: cloud ML model → pgvector, with OCR fallback.
 */
export async function supabaseScan(
  imageFile: File | Blob,
  topK = 5,
  lang: ScanLanguage = 'en',
): Promise<ScanResult> {
  // 1. Try cloud model
  const embedding = await cloudEmbedding(imageFile);

  if (embedding) {
    // 2. Query Supabase pgvector — fetch extra results so we can filter by language
    const embeddingStr = '[' + embedding.join(',') + ']';

    const { data, error } = await supabase.rpc('match_card', {
      query_embedding: embeddingStr,
      match_count: topK * 3,
    });

    if (!error && data && data.length > 0) {
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

      const matches = filterByLanguage(allMatches, lang).slice(0, topK);

      if (matches.length > 0) {
        if (lang === 'ja') await enrichWithEnglishNames(matches);

        return {
          matches,
          ocr_text: '',
          method_used: 'visual',
          visual_index_size: 0,
          catalog_size: 0,
        };
      }
    }
  }

  // 3. Fallback to OCR → fuzzy search
  return ocrFallback(imageFile, topK, lang);
}
