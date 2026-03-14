/**
 * Supabase-backed card scanning.
 *
 * Pipeline:
 *   1. Run MobileNetV3-Small ONNX on-device → 576-D embedding
 *   2. Send embedding to Supabase `match_card` RPC (pgvector cosine search)
 *   3. Return top-K matches
 *
 * No Python backend required — all ML inference is on-device,
 * all matching is in Supabase Postgres.
 */

import { supabase } from '../lib/supabase';
import { visualMatchService } from './visualMatchService';
import type { ScanMatch, ScanResult } from './cardScanService';

/** Ensure the ONNX model is loaded (one-time). */
let _initPromise: Promise<void> | null = null;

function ensureModel(): Promise<void> {
  if (!_initPromise) {
    _initPromise = visualMatchService.init().then(() => {});
  }
  return _initPromise;
}

/**
 * Scan a card image using on-device ONNX + Supabase pgvector.
 */
export async function supabaseScan(
  imageFile: File | Blob,
  topK = 5,
): Promise<ScanResult> {
  // 1. Ensure model is loaded
  await ensureModel();

  // 2. Extract embedding on-device
  const embedding = await visualMatchService.extractEmbedding(imageFile);
  if (!embedding) {
    return {
      matches: [],
      ocr_text: '',
      method_used: 'none',
      visual_index_size: 0,
      catalog_size: 0,
    };
  }

  // 3. Query Supabase pgvector
  const embeddingStr = '[' + Array.from(embedding).join(',') + ']';

  const { data, error } = await supabase.rpc('match_card', {
    query_embedding: embeddingStr,
    match_count: topK,
  });

  if (error) {
    console.error('[supabaseScan] pgvector query failed:', error);
    return {
      matches: [],
      ocr_text: '',
      method_used: 'none',
      visual_index_size: 0,
      catalog_size: 0,
    };
  }

  // 4. Map results to ScanMatch format
  const matches: ScanMatch[] = (data ?? []).map((row) => ({
    id: row.id,
    name: row.name,
    number: row.number,
    set_id: row.set_id,
    set_name: '', // set name not returned by RPC; UI can look it up if needed
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

  return {
    matches,
    ocr_text: '',
    method_used: matches.length > 0 ? 'visual' : 'none',
    visual_index_size: 0,
    catalog_size: 0,
  };
}
