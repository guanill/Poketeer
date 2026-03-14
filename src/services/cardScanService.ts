import { isNativePlatform } from '../utils/platform';
import { nativeScanCard, nativeCheckHealth } from './nativeScanService';
import { supabaseScan } from './supabaseScanService';

export interface ScanMatch {
  id: string;
  name: string;
  number: string;
  set_id: string;
  set_name: string;
  rarity: string;
  image_small: string;
  image_large: string;
  supertype: string;
  subtypes: string[];
  hp: string;
  artist: string;
  confidence: number;
  method: 'ocr' | 'visual' | 'ocr+visual';
}

export interface ScanResult {
  matches: ScanMatch[];
  ocr_text: string;
  method_used: 'ocr' | 'visual' | 'combined' | 'none';
  visual_index_size: number;
  catalog_size: number;
}

export interface IndexStats {
  index_size: number;
  index_path: string;
  index_exists: boolean;
}

export const cardScanService = {
  /**
   * Scan a card image and return top-K matches.
   *
   * Pipeline (web):
   *   1. Run ONNX model on-device → 576-D embedding
   *   2. Query Supabase pgvector RPC → top-K similar cards
   *
   * Pipeline (native / mobile):
   *   Same as web, with Tesseract OCR as a supplementary signal.
   */
  async scanCard(imageFile: File | Blob, topK = 5): Promise<ScanResult> {
    if (isNativePlatform()) return nativeScanCard(imageFile, topK);

    // Web: on-device ONNX → Supabase pgvector
    return supabaseScan(imageFile, topK);
  },

  async getIndexStats(): Promise<IndexStats> {
    return { index_size: 0, index_path: 'supabase-pgvector', index_exists: true };
  },

  async checkHealth(): Promise<boolean> {
    if (isNativePlatform()) return nativeCheckHealth();
    // Supabase is always available (no local backend needed)
    return true;
  },
};
