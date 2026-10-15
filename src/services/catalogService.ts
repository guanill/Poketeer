/**
 * Offline catalog service — loads public/catalog.json (bundled in the APK)
 * and provides set/card lookup + Fuse.js fuzzy search.
 *
 * On native the catalog is the ONLY data source (no network needed).
 * On desktop it is never used (pokemonTCG.ts handles everything).
 */

import Fuse, { type FuseResult } from 'fuse.js';
import type { PokemonCard, PokemonSet } from '../types';
import type { CardsResponse, SetsResponse } from './pokemonTCG';
import type { ScanMatch } from './cardScanService';

// ── Catalog types ─────────────────────────────────────────────────────────────

interface Catalog {
  version: number;
  generatedAt: string;
  sets: PokemonSet[];
  cards: PokemonCard[];
}

// ── Singleton state ───────────────────────────────────────────────────────────

let _catalog: Catalog | null = null;
let _loading: Promise<Catalog> | null = null;
let _fuse: Fuse<PokemonCard> | null = null;
// Pre-grouped cards by setId for fast getCardsBySet
const _bySet: Record<string, PokemonCard[]> = {};
const _byId: Record<string, PokemonCard> = {};
// Pre-grouped cards by normalized card number for number-based lookup
const _byNumber: Record<string, PokemonCard[]> = {};

function nameSimilarity(a: string, b: string): number {
  const normalize = (value: string) => value
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]/gu, '');
  const left = normalize(a);
  const right = normalize(b);
  if (left === right) return 1;
  if (!left || !right) return 0;
  if (left.includes(right) || right.includes(left)) {
    return Math.min(left.length, right.length) / Math.max(left.length, right.length);
  }

  let previous = Array.from({ length: right.length + 1 }, (_, i) => i);
  for (let i = 1; i <= left.length; i++) {
    const current = [i];
    for (let j = 1; j <= right.length; j++) {
      current[j] = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (left[i - 1] === right[j - 1] ? 0 : 1),
      );
    }
    previous = current;
  }
  return 1 - previous[right.length] / Math.max(left.length, right.length);
}

async function loadCatalog(): Promise<Catalog> {
  if (_catalog) return _catalog;
  if (_loading) return _loading;

  _loading = (async () => {
    // In Capacitor, assets are served relative to index.html
    const res = await fetch('./catalog.json');
    if (!res.ok) throw new Error(`catalog.json not found (${res.status})`);
    const data: Catalog = await res.json();

    // Build lookup structures
    for (const card of data.cards) {
      _byId[card.id] = card;
      if (!_bySet[card.set.id]) _bySet[card.set.id] = [];
      _bySet[card.set.id].push(card);
      // Number index: strip leading zeros so "025" == "25"
      const numKey = card.number.replace(/^0+/, '').toLowerCase();
      if (!_byNumber[numKey]) _byNumber[numKey] = [];
      _byNumber[numKey].push(card);
    }

    // Build Fuse index on card names (threshold 0.45 = tolerant of OCR errors)
    _fuse = new Fuse(data.cards, {
      keys: ['name'],
      threshold: 0.45,
      includeScore: true,
      minMatchCharLength: 2,
      ignoreLocation: true,
    });

    _catalog = data;
    _loading = null;
    return data;
  })();

  return _loading;
}

// ── Public API ────────────────────────────────────────────────────────────────

export const catalogService = {
  /** Pre-load the catalog in the background (call on app start). */
  prewarm(): void {
    loadCatalog().catch(() => {}); // fire and forget
  },

  async getSets(): Promise<SetsResponse> {
    const cat = await loadCatalog();
    return { data: cat.sets, totalCount: cat.sets.length };
  },

  async getSet(setId: string): Promise<PokemonSet | null> {
    const cat = await loadCatalog();
    return cat.sets.find(s => s.id === setId) ?? null;
  },

  async getCardsBySet(setId: string, page = 1, pageSize = 60): Promise<CardsResponse> {
    await loadCatalog();
    const all = _bySet[setId] ?? [];
    const start = (page - 1) * pageSize;
    const slice = all.slice(start, start + pageSize);
    return {
      data: slice,
      totalCount: all.length,
      page,
      pageSize,
      count: slice.length,
    };
  },

  async searchCards(query: string, page = 1, pageSize = 30): Promise<CardsResponse> {
    await loadCatalog();
    if (!_fuse) return { data: [], totalCount: 0, page, pageSize, count: 0 };

    const results = _fuse.search(query);
    const all = results.map(r => r.item);
    const start = (page - 1) * pageSize;
    const slice = all.slice(start, start + pageSize);
    return {
      data: slice,
      totalCount: all.length,
      page,
      pageSize,
      count: slice.length,
    };
  },

  async getCardsByIds(ids: string[]): Promise<PokemonCard[]> {
    await loadCatalog();
    return ids.map(id => _byId[id]).filter(Boolean);
  },

  /** Used by nativeScanService: fuzzy-match a raw OCR text against all card names. */
  async fuzzySearchByName(rawText: string, topK = 8): Promise<ScanMatch[]> {
    await loadCatalog();
    if (!_fuse || !rawText.trim()) return [];

    // Try progressively shorter queries until we get hits
    const words = rawText.trim().split(/\s+/);
    let results: FuseResult<PokemonCard>[] = [];

    for (let take = words.length; take >= 1; take--) {
      const q = words.slice(0, take).join(' ');
      if (q.length < 2) continue;
      results = _fuse.search(q, { limit: topK + 4 });
      if (results.length > 0) break;
    }

    return results.slice(0, topK).map((r, i) => {
      const card = r.item;
      const fuseScore = r.score ?? 0.5; // 0 = perfect, 1 = no match
      const confidence = Math.max(0.05, Math.min(0.97, 1 - fuseScore - i * 0.03));
      return {
        id: card.id,
        name: card.name,
        number: card.number,
        set_id: card.set.id,
        set_name: card.set.name,
        rarity: card.rarity ?? '',
        image_small: card.images.small,
        image_large: card.images.large,
        supertype: card.supertype,
        subtypes: card.subtypes ?? [],
        hp: card.hp ?? '',
        artist: card.artist ?? '',
        confidence,
        method: 'ocr',
      };
    });
  },

  /**
   * Look up cards by their printed number (e.g. "4", "025", "SWSH025").
   * Optionally cross-rank by name similarity when a name hint is provided.
   */
  async searchByNumber(rawNumber: string, nameHint = '', topK = 8): Promise<ScanMatch[]> {
    await loadCatalog();
    const key = rawNumber.replace(/^0+/, '').toLowerCase();
    const candidates = _byNumber[key] ?? [];
    if (candidates.length === 0) return [];

    const ranked = nameHint
      ? candidates
        .map(card => ({ card, similarity: nameSimilarity(nameHint, card.name) }))
        .sort((a, b) => b.similarity - a.similarity)
      : candidates.map(card => ({ card, similarity: 0 }));

    return ranked.slice(0, topK).map(({ card, similarity }) => ({
      id: card.id,
      name: card.name,
      number: card.number,
      set_id: card.set.id,
      set_name: card.set.name,
      rarity: card.rarity ?? '',
      image_small: card.images.small,
      image_large: card.images.large,
      supertype: card.supertype,
      subtypes: card.subtypes ?? [],
      hp: card.hp ?? '',
      artist: card.artist ?? '',
      confidence: nameHint ? 0.35 + similarity * 0.6 : 0.68,
      method: 'ocr',
    }));
  },
};
