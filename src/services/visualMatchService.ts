/**
 * On-device visual card matching using ONNX Runtime Web.
 *
 * Pipeline:
 *  1. Load MobileNetV3-Small ONNX model (~4 MB, fast on mobile WASM)
 *  2. Load quantized card feature index (~11 MB, bundled in APK)
 *  3. Preprocess scanned card image -> model input tensor
 *  4. Run inference -> 576-D L2-normalised embedding
 *  5. Cosine similarity against all indexed cards
 *  6. Return top-K matches
 *
 * All computation is local -- no network calls at scan time.
 */

import * as ort from 'onnxruntime-web';
import type { ScanMatch } from './cardScanService';

// ── Types ────────────────────────────────────────────────────────────────────

interface CardMeta {
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
}

// ── Constants ────────────────────────────────────────────────────────────────

const MODEL_PATH = './card_model.onnx';
const INDEX_PATH = './card_index_mobile.bin';
const META_PATH = './card_index_meta.json';

const INPUT_SIZE = 224;

// ImageNet normalization constants
const MEAN = [0.485, 0.456, 0.406];
const STD = [0.229, 0.224, 0.225];

// ── State ────────────────────────────────────────────────────────────────────

let _session: ort.InferenceSession | null = null;
let _indexData: Uint8Array | null = null;
let _indexMins: Float32Array | null = null;
let _indexMaxs: Float32Array | null = null;
let _indexDim = 0;
let _indexN = 0;
let _metadata: CardMeta[] | null = null;
let _ready = false;
let _loading: Promise<boolean> | null = null;
let _modelOnlySession: ort.InferenceSession | null = null;

// ── Initialization ───────────────────────────────────────────────────────────

async function loadModel(): Promise<ort.InferenceSession> {
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = './';

  const session = await ort.InferenceSession.create(MODEL_PATH, {
    executionProviders: ['wasm'],
    graphOptimizationLevel: 'all',
  });
  return session;
}

async function loadIndex(): Promise<void> {
  const res = await fetch(INDEX_PATH);
  if (!res.ok) throw new Error(`Failed to load index: ${res.status}`);
  const buffer = await res.arrayBuffer();

  // Parse header: [n_cards:u32] [dim:u32]
  const header = new Uint32Array(buffer, 0, 2);
  _indexN = header[0];
  _indexDim = header[1];

  // Parse mins/maxs for dequantization
  const headerBytes = 8;
  _indexMins = new Float32Array(buffer, headerBytes, _indexDim);
  _indexMaxs = new Float32Array(buffer, headerBytes + _indexDim * 4, _indexDim);

  // Parse quantized features
  const dataOffset = headerBytes + _indexDim * 4 * 2;
  _indexData = new Uint8Array(buffer, dataOffset, _indexN * _indexDim);
}

async function loadMetadata(): Promise<void> {
  const res = await fetch(META_PATH);
  if (!res.ok) throw new Error(`Failed to load metadata: ${res.status}`);
  _metadata = await res.json();
}

async function initialize(): Promise<boolean> {
  try {
    const [session] = await Promise.all([
      loadModel(),
      loadIndex(),
      loadMetadata(),
    ]);
    _session = session;

    // Validate that model output dimension matches the index dimension.
    // A mismatch means the index was built with a different model and
    // cosine similarity scores would be meaningless.
    const dummy = new Float32Array(3 * INPUT_SIZE * INPUT_SIZE);
    const dummyTensor = new ort.Tensor('float32', dummy, [1, 3, INPUT_SIZE, INPUT_SIZE]);
    const testOut = await session.run({ image: dummyTensor });
    const modelDim = (testOut.features.data as Float32Array).length;

    if (modelDim !== _indexDim) {
      console.error(
        `[visualMatch] DIMENSION MISMATCH: model outputs ${modelDim}-D but index has ${_indexDim}-D features. ` +
        `Rebuild the index with: python -m backend.training.export_mobile_onnx`
      );
      _ready = false;
      return false;
    }

    _ready = true;
    console.log(`[visualMatch] Ready: ${_indexN} cards indexed (${_indexDim}-D)`);
    return true;
  } catch (err) {
    console.warn('[visualMatch] Not available:', err);
    _ready = false;
    return false;
  }
}

// ── Image preprocessing ──────────────────────────────────────────────────────

function preprocessImage(imageData: ImageData): Float32Array {
  const { data, width, height } = imageData;
  const tensor = new Float32Array(3 * INPUT_SIZE * INPUT_SIZE);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const srcIdx = (y * width + x) * 4;
      const r = data[srcIdx] / 255;
      const g = data[srcIdx + 1] / 255;
      const b = data[srcIdx + 2] / 255;

      const dstIdx = y * width + x;
      tensor[0 * INPUT_SIZE * INPUT_SIZE + dstIdx] = (r - MEAN[0]) / STD[0];
      tensor[1 * INPUT_SIZE * INPUT_SIZE + dstIdx] = (g - MEAN[1]) / STD[1];
      tensor[2 * INPUT_SIZE * INPUT_SIZE + dstIdx] = (b - MEAN[2]) / STD[2];
    }
  }

  return tensor;
}

function imageToTensor(imageFile: File | Blob): Promise<Float32Array> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(imageFile);

    img.onload = () => {
      URL.revokeObjectURL(url);

      const canvas = document.createElement('canvas');
      canvas.width = INPUT_SIZE;
      canvas.height = INPUT_SIZE;
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(img, 0, 0, INPUT_SIZE, INPUT_SIZE);
      const imageData = ctx.getImageData(0, 0, INPUT_SIZE, INPUT_SIZE);

      resolve(preprocessImage(imageData));
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Failed to load image'));
    };

    img.src = url;
  });
}

// ── Inference + matching ─────────────────────────────────────────────────────

function cosineSimilarity(query: Float32Array, topK: number): { index: number; score: number }[] {
  if (!_indexData || !_indexMins || !_indexMaxs) throw new Error('Index not loaded');

  // Query is already L2-normalised by the model, but compute norm for safety
  let queryNorm = 0;
  for (let i = 0; i < _indexDim; i++) queryNorm += query[i] * query[i];
  queryNorm = Math.sqrt(queryNorm);
  if (queryNorm === 0) return [];

  const scores: { index: number; score: number }[] = [];

  for (let n = 0; n < _indexN; n++) {
    let dot = 0;
    let cardNorm = 0;
    const offset = n * _indexDim;

    for (let d = 0; d < _indexDim; d++) {
      // Dequantize
      const qVal = _indexData[offset + d];
      const range = _indexMaxs[d] - _indexMins[d];
      const val = range > 0 ? _indexMins[d] + (qVal / 255) * range : _indexMins[d];

      dot += query[d] * val;
      cardNorm += val * val;
    }

    cardNorm = Math.sqrt(cardNorm);
    const sim = cardNorm > 0 ? dot / (queryNorm * cardNorm) : 0;
    scores.push({ index: n, score: sim });
  }

  scores.sort((a, b) => b.score - a.score);
  return scores.slice(0, topK);
}

// ── Public API ───────────────────────────────────────────────────────────────

export const visualMatchService = {
  /** Initialize the visual matching engine. Call once at app start. */
  async init(): Promise<boolean> {
    if (_ready) return true;
    if (_loading) return _loading;
    _loading = initialize();
    return _loading;
  },

  /** Check if the visual matching engine is ready. */
  isReady(): boolean {
    return _ready;
  },

  /**
   * Extract a 576-D embedding from an image without matching against the local index.
   * Used by supabaseScanService to query pgvector server-side.
   */
  async extractEmbedding(imageFile: File | Blob): Promise<Float32Array | null> {
    if (!_session) {
      // Try to load just the model (without index) for embedding-only mode
      if (!_modelOnlySession) {
        try {
          _modelOnlySession = await loadModel();
        } catch {
          return null;
        }
      }
    }
    const session = _session ?? _modelOnlySession;
    if (!session) return null;

    const tensor = await imageToTensor(imageFile);
    const inputTensor = new ort.Tensor('float32', tensor, [1, 3, INPUT_SIZE, INPUT_SIZE]);
    const results = await session.run({ image: inputTensor });
    return results.features.data as Float32Array;
  },

  /** Match a card image against the local index. Returns top-K matches. */
  async matchCard(imageFile: File | Blob, topK = 5): Promise<ScanMatch[]> {
    if (!_ready || !_session || !_metadata) return [];

    // Preprocess image
    const tensor = await imageToTensor(imageFile);
    const inputTensor = new ort.Tensor('float32', tensor, [1, 3, INPUT_SIZE, INPUT_SIZE]);

    // Run inference — model outputs L2-normalised 576-D embeddings
    const results = await _session.run({ image: inputTensor });
    const features = results.features.data as Float32Array;

    // Direct cosine similarity against indexed card features
    const topMatches = cosineSimilarity(features, topK);

    return topMatches.map((m) => {
      const card = _metadata![m.index];
      const confidence = Math.max(0, Math.min(0.99, m.score));
      return {
        id: card.id,
        name: card.name,
        number: card.number,
        set_id: card.set_id,
        set_name: card.set_name,
        rarity: card.rarity,
        image_small: card.image_small,
        image_large: card.image_large,
        supertype: card.supertype,
        subtypes: card.subtypes,
        hp: card.hp,
        artist: card.artist,
        confidence: Math.round(confidence * 1000) / 1000,
        method: 'visual' as const,
      };
    });
  },
};
