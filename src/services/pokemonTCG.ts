import type { PokemonCard, PokemonSet } from '../types';
import { isNativePlatform } from '../utils/platform';
import { catalogService } from './catalogService';
import { visualMatchService } from './visualMatchService';
import { supabase } from '../lib/supabase';

// Pre-load catalog + visual model on native so first scan is fast
if (isNativePlatform()) {
  catalogService.prewarm();
  visualMatchService.init().catch(() => {}); // fire and forget
}

// ---------------------------------------------------------------------------
// Shared types (re-exported so other files can keep importing from here)
// ---------------------------------------------------------------------------

export interface SetsResponse {
  data: PokemonSet[];
  totalCount: number;
}

export interface CardsResponse {
  data: PokemonCard[];
  totalCount: number;
  page: number;
  pageSize: number;
  count: number;
}

// ---------------------------------------------------------------------------
// Row → frontend shape mappers
// ---------------------------------------------------------------------------

/** Map a Supabase `sets` row to the PokemonSet interface the UI expects. */
function rowToSet(row: {
  id: string;
  name: string;
  series: string;
  printed_total: number;
  total: number;
  release_date: string;
  language: string;
  symbol_url: string;
  logo_url: string;
}): PokemonSet {
  return {
    id: row.id,
    name: row.name,
    series: row.series,
    printedTotal: row.printed_total,
    total: row.total,
    releaseDate: row.release_date,
    language: row.language as PokemonSet['language'],
    images: { symbol: row.symbol_url, logo: row.logo_url },
  };
}

/** Map a Supabase `cards` row (joined with its set) to PokemonCard. */
function rowToCard(row: {
  id: string;
  name: string;
  number: string;
  set_id: string;
  rarity: string;
  image_small: string;
  image_large: string;
  supertype: string;
  subtypes: string[];
  hp: string;
  artist: string;
  types: string[];
  sets?: {
    id: string;
    name: string;
    series: string;
    symbol_url: string;
    logo_url: string;
  } | null;
}): PokemonCard {
  const s = row.sets;
  return {
    id: row.id,
    name: row.name,
    number: row.number,
    supertype: row.supertype,
    subtypes: row.subtypes,
    hp: row.hp,
    types: row.types,
    artist: row.artist,
    rarity: row.rarity,
    set: {
      id: s?.id ?? row.set_id,
      name: s?.name ?? '',
      series: s?.series ?? '',
      images: { symbol: s?.symbol_url ?? '', logo: s?.logo_url ?? '' },
    },
    images: { small: row.image_small, large: row.image_large },
  };
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

export const pokemonTCGService = {
  async getSets(lang: 'en' | 'ja' | 'th' = 'en'): Promise<PokemonSet[]> {
    if (isNativePlatform()) {
      if (lang === 'ja' || lang === 'th') return [];
      const res = await catalogService.getSets();
      return res.data;
    }

    const { data, error } = await supabase
      .from('sets')
      .select('*')
      .eq('language', lang)
      .order('release_date', { ascending: false });

    if (error) throw error;
    return (data ?? []).map(rowToSet);
  },

  async getSet(setId: string, lang: string = 'en'): Promise<PokemonSet> {
    if (isNativePlatform()) {
      const s = await catalogService.getSet(setId);
      if (s) return s;
      throw new Error(`Set ${setId} not found in local catalog`);
    }

    // Try the requested language first, then fall back to any language
    const { data, error } = await supabase
      .from('sets')
      .select('*')
      .eq('id', setId)
      .order('language', { ascending: lang === 'en' }) // prefer requested lang
      .limit(1)
      .single();

    if (error) throw new Error(`Set ${setId} not found`);
    return rowToSet(data);
  },

  async getCardsBySet(setId: string, page = 1, pageSize = 60): Promise<CardsResponse> {
    if (isNativePlatform()) {
      return catalogService.getCardsBySet(setId, page, pageSize);
    }

    const from = (page - 1) * pageSize;
    const to = from + pageSize - 1;

    // Get total count
    const { count } = await supabase
      .from('cards')
      .select('id', { count: 'exact', head: true })
      .eq('set_id', setId);

    // Get page of cards with set join
    const { data, error } = await supabase
      .from('cards')
      .select('*, sets!inner(id, name, series, symbol_url, logo_url)')
      .eq('set_id', setId)
      .order('number')
      .range(from, to);

    if (error) throw error;
    const cards = (data ?? []).map(rowToCard);

    return {
      data: cards,
      totalCount: count ?? 0,
      page,
      pageSize,
      count: cards.length,
    };
  },

  async getCard(cardId: string): Promise<PokemonCard> {
    const { data, error } = await supabase
      .from('cards')
      .select('*, sets!inner(id, name, series, symbol_url, logo_url)')
      .eq('id', cardId)
      .single();

    if (error) throw new Error(`Card ${cardId} not found`);
    return rowToCard(data);
  },

  async searchCards(query: string, page = 1, pageSize = 30): Promise<CardsResponse> {
    if (isNativePlatform()) {
      return catalogService.searchCards(query, page, pageSize);
    }

    const from = (page - 1) * pageSize;

    // Use the fuzzy search RPC for trigram-based matching
    const { data, error } = await supabase
      .rpc('search_cards_fuzzy', {
        query,
        result_limit: pageSize,
        result_offset: from,
      });

    if (error) throw error;

    // search_cards_fuzzy returns flat rows — map to PokemonCard shape
    const cards: PokemonCard[] = (data ?? []).map((row: {
      id: string; name: string; number: string; set_id: string;
      rarity: string; image_small: string; image_large: string;
      supertype: string; subtypes: string[]; hp: string;
      artist: string; types: string[]; similarity: number;
    }) => ({
      id: row.id,
      name: row.name,
      number: row.number,
      supertype: row.supertype,
      subtypes: row.subtypes,
      hp: row.hp,
      types: row.types,
      artist: row.artist,
      rarity: row.rarity,
      set: { id: row.set_id, name: '', series: '', images: { symbol: '', logo: '' } },
      images: { small: row.image_small, large: row.image_large },
    }));

    // We don't have an exact total from the RPC — estimate
    const totalCount = cards.length < pageSize ? from + cards.length : from + cards.length + 1;

    return { data: cards, totalCount, page, pageSize, count: cards.length };
  },

  async getIntlCardsBySet(lang: 'ja' | 'th', setId: string, page = 1, pageSize = 60): Promise<CardsResponse> {
    if (isNativePlatform()) return { data: [], totalCount: 0, page, pageSize, count: 0 };

    // International cards live in the same cards table, linked to sets with the right language
    // If they haven't been seeded, the result will be empty
    return this.getCardsBySet(setId, page, pageSize);
  },

  async getPrices(cardIds: string[]): Promise<Record<string, number | null>> {
    if (cardIds.length === 0 || isNativePlatform()) return {};

    const { data, error } = await supabase
      .from('prices_cache')
      .select('card_id, market_price')
      .in('card_id', cardIds);

    if (error) return {};

    const result: Record<string, number | null> = {};
    for (const row of data ?? []) {
      result[row.card_id] = row.market_price;
    }
    return result;
  },

  async getCardsByIds(cardIds: string[]): Promise<PokemonCard[]> {
    if (cardIds.length === 0) return [];
    if (isNativePlatform()) {
      return catalogService.getCardsByIds(cardIds);
    }

    const { data, error } = await supabase
      .from('cards')
      .select('*, sets!inner(id, name, series, symbol_url, logo_url)')
      .in('id', cardIds);

    if (error) throw error;
    return (data ?? []).map(rowToCard);
  },
};

// ---------------------------------------------------------------------------
// Utility functions (unchanged — used by CardItem, CardDetailModal, etc.)
// ---------------------------------------------------------------------------

export function getCardMarketPrice(card: PokemonCard): number | null {
  const prices = card.tcgplayer?.prices;
  if (!prices) return null;
  return (
    prices.holofoil?.market ??
    prices.normal?.market ??
    prices.reverseHolofoil?.market ??
    prices['1stEditionHolofoil']?.market ??
    null
  );
}

export function getRarityColor(rarity?: string): string {
  if (!rarity) return '#9ca3af';
  const r = rarity.toLowerCase();
  if (r.includes('secret') || r.includes('rainbow') || r.includes('hyper')) return '#ef4444';
  if (r.includes('ultra') || r.includes('full art') || r.includes('gold')) return '#8b5cf6';
  if (r.includes('rare holo vmax') || r.includes('vstar')) return '#6366f1';
  if (r.includes('rare holo v') || r.includes('ex') || r.includes('gx')) return '#a855f7';
  if (r.includes('rare holo') || r.includes('special')) return '#3b82f6';
  if (r.includes(' rare')) return '#60a5fa';
  if (r.includes('uncommon')) return '#10b981';
  return '#9ca3af';
}

export function getTypeGradient(types?: string[]): string {
  const typeMap: Record<string, string> = {
    fire: 'from-orange-600 to-red-500',
    water: 'from-blue-400 to-cyan-400',
    grass: 'from-green-500 to-emerald-400',
    electric: 'from-yellow-400 to-amber-400',
    psychic: 'from-pink-500 to-purple-500',
    ice: 'from-cyan-300 to-blue-300',
    dragon: 'from-indigo-600 to-purple-600',
    dark: 'from-gray-700 to-gray-900',
    fairy: 'from-pink-400 to-rose-300',
    fighting: 'from-red-700 to-orange-800',
    poison: 'from-purple-600 to-violet-700',
    ground: 'from-yellow-600 to-amber-700',
    flying: 'from-blue-300 to-indigo-300',
    bug: 'from-green-600 to-lime-600',
    rock: 'from-yellow-700 to-stone-600',
    ghost: 'from-indigo-700 to-purple-800',
    steel: 'from-slate-400 to-gray-500',
    normal: 'from-gray-400 to-gray-500',
    colorless: 'from-gray-300 to-gray-400',
  };
  const type = (types?.[0] ?? 'normal').toLowerCase();
  return typeMap[type] ?? 'from-gray-500 to-gray-600';
}
