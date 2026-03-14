import { useState, useMemo, useDeferredValue, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, SlidersHorizontal, Layers, Globe } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import type { PokemonSet } from '../types';
import { SetCard } from '../components/SetCard';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useCollectionStore } from '../store/collectionStore';

// Stable empty array so SetCard memo doesn't see a new reference each render
const EMPTY: string[] = [];

type Lang = 'en' | 'ja' | 'th';

const LANG_LABELS: Record<Lang, { flag: string; label: string }> = {
  en: { flag: '🇬🇧', label: 'English' },
  ja: { flag: '🇯🇵', label: 'Japanese' },
  th: { flag: '🇹🇭', label: 'Thai' },
};

export function Sets() {
  const [lang, setLang] = useState<Lang>('en');
  const [search, setSearch] = useState('');
  const [seriesFilter, setSeriesFilter] = useState('All');
  const [sortBy, setSortBy] = useState<'date' | 'name' | 'progress'>('date');
  const [showFilters, setShowFilters] = useState(false);

  // Deferred so typing is always instant — filtering runs one frame later
  const deferredSearch = useDeferredValue(search);
  const deferredSeries = useDeferredValue(seriesFilter);
  const deferredSort   = useDeferredValue(sortBy);

  const owned = useCollectionStore(s => s.owned);
  const queryClient = useQueryClient();

  // Fetch sets for the active language. `select` filters inside TanStack Query —
  // it's bound to this query key, so it can never show data from another language.
  const selectForLang = useCallback(
    (data: PokemonSet[]) =>
      lang === 'en'
        ? data.filter(s => !s.language || s.language === 'en')
        : data.filter(s => s.language === lang),
    [lang],
  );

  const { data: sets, isLoading } = useQuery({
    queryKey: ['sets', 'v2', lang],
    queryFn: () => pokemonTCGService.getSets(lang),
    staleTime: 1000 * 60 * 10,
    gcTime: 1000 * 60 * 15,
    placeholderData: undefined,
    select: selectForLang,
  });

  useEffect(() => {
    // Prefetch the other two languages in the background so switching is instant
    (['en', 'ja', 'th'] as Lang[]).filter(l => l !== lang).forEach(l => {
      queryClient.prefetchQuery({
        queryKey: ['sets', 'v2', l],
        queryFn: () => pokemonTCGService.getSets(l),
        staleTime: 1000 * 60 * 10,
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLangChange = (l: Lang) => {
    setLang(l);
    setSearch('');
    setSeriesFilter('All');
    // Fire-and-forget: warm the card cache for the first visible sets
    if (l === 'ja' || l === 'th') {
      queryClient.fetchQuery({
        queryKey: ['sets', 'v2', l],
        queryFn: () => pokemonTCGService.getSets(l),
        staleTime: 1000 * 60 * 10,
      }).then((allSets) => {
        const ids = allSets.slice(0, 20).map(s => s.id).join(',');
        fetch(`http://localhost:8000/intl-cards-prefetch/${l}?ids=${encodeURIComponent(ids)}`)
          .catch(() => { /* best-effort */ });
      }).catch(() => { /* best-effort */ });
    }
  };

  // Get all unique series
  const seriesList = useMemo(() => {
    if (!sets) return [];
    const s = [...new Set(sets.map(set => set.series))].sort();
    return ['All', ...s];
  }, [sets]);

  // Owned card IDs grouped by set
  const ownedBySet = useMemo(() => {
    const map: Record<string, string[]> = {};
    Object.keys(owned).forEach(cardId => {
      const parts = cardId.split('-');
      const setId = parts.length >= 2 ? parts.slice(0, parts.length - 1).join('-') : parts[0];
      if (!map[setId]) map[setId] = [];
      map[setId].push(cardId);
    });
    return map;
  }, [owned]);

  const filteredSets = useMemo(() => {
    if (!sets) return [];
    const q = deferredSearch.toLowerCase();
    let result = sets.filter(s => {
      const matchesSearch = !q ||
        s.name.toLowerCase().includes(q) ||
        s.series.toLowerCase().includes(q);
      const matchesSeries = deferredSeries === 'All' || s.series === deferredSeries;
      return matchesSearch && matchesSeries;
    });

    if (deferredSort === 'name') {
      result = [...result].sort((a, b) => a.name.localeCompare(b.name));
    } else if (deferredSort === 'progress') {
      result = [...result].sort((a, b) => {
        const aOwned = (ownedBySet[a.id] ?? []).length;
        const bOwned = (ownedBySet[b.id] ?? []).length;
        const aP = a.total > 0 ? aOwned / a.total : 0;
        const bP = b.total > 0 ? bOwned / b.total : 0;
        return bP - aP;
      });
    }
    return result;
  }, [sets, deferredSearch, deferredSeries, deferredSort, ownedBySet]);

  const startedSets = filteredSets.filter(s => (ownedBySet[s.id] ?? []).length > 0).length;

  return (
    <div className="space-y-6">

      {/* ── Header ───────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="page-section-label mb-1.5">TCG Library</p>
          <h1 className="text-3xl font-black flex items-center gap-2.5">
            <Layers size={26} className="text-amber-400 shrink-0" />
            <span className="text-gradient-gold">{LANG_LABELS[lang].label}</span>
            <span className="text-white"> Sets</span>
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {sets ? (
              <>
                <span className="text-amber-400/80 font-bold">{sets.length}</span> sets ·{' '}
                <span className="text-violet-400/80 font-bold">{startedSets}</span> started
              </>
            ) : 'Loading…'}
          </p>
        </div>

        {/* Language switcher */}
        <div
          className="flex gap-1 p-1 rounded-2xl"
          style={{
            background: 'linear-gradient(145deg, #13132a, #0f0f22)',
            border: '1px solid rgba(139,92,246,0.15)',
          }}
        >
          {(Object.keys(LANG_LABELS) as Lang[]).map(l => (
            <motion.button
              key={l}
              whileTap={{ scale: 0.96 }}
              onClick={() => handleLangChange(l)}
              className={`lang-tab ${lang === l ? 'lang-tab-active' : ''}`}
            >
              <Globe size={13} />
              <span>{LANG_LABELS[l].flag}</span>
              {LANG_LABELS[l].label}
            </motion.button>
          ))}
        </div>
      </div>

      <div className="gradient-divider" />

      {/* ── Search & Filters ─────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
            <input
              type="text"
              placeholder="Search sets or series…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="tcg-input w-full pl-10 pr-4 py-2.5 text-sm"
            />
          </div>
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={() => setShowFilters(v => !v)}
            className={`sort-pill flex items-center gap-1.5 px-4 ${showFilters ? 'sort-pill-amber' : ''}`}
          >
            <SlidersHorizontal size={14} />
            Filters
          </motion.button>
        </div>

        <AnimatePresence>
          {showFilters && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="filter-panel p-4 space-y-4">
                {/* Sort */}
                <div>
                  <p className="page-section-label mb-2.5">Order By</p>
                  <div className="flex gap-2 flex-wrap">
                    {(['date', 'name', 'progress'] as const).map(opt => (
                      <button
                        key={opt}
                        onClick={() => setSortBy(opt)}
                        className={`sort-pill capitalize ${sortBy === opt ? 'sort-pill-active' : ''}`}
                      >
                        {opt === 'date' ? '📅 Date' : opt === 'name' ? '🔤 Name' : '📊 Progress'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Series */}
                <div>
                  <p className="page-section-label mb-2.5">Series</p>
                  <div className="flex flex-wrap gap-1.5">
                    {seriesList.map(s => (
                      <button
                        key={s}
                        onClick={() => setSeriesFilter(s)}
                        className={`series-badge ${seriesFilter === s ? 'series-badge-active' : ''}`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Sets Grid ────────────────────────────────────── */}
      {isLoading ? (
        <LoadingSkeleton count={12} type="set" />
      ) : (
        <AnimatePresence mode="popLayout">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredSets.map((set, i) => (
              <SetCard
                key={set.id}
                set={set}
                index={i}
                ownedCardIds={ownedBySet[set.id] ?? EMPTY}
              />
            ))}
          </div>
        </AnimatePresence>
      )}

      {/* Empty state */}
      {!isLoading && filteredSets.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center py-20 rounded-2xl"
          style={{
            background: 'linear-gradient(145deg, #111128, #0d0d20)',
            border: '1px solid rgba(139,92,246,0.1)',
          }}
        >
          <div className="text-5xl mb-4 opacity-40">🃏</div>
          <p className="text-gray-400 font-semibold">No sets matched your search</p>
          <p className="text-gray-600 text-sm mt-1">Try adjusting your filters</p>
          <button
            onClick={() => { setSearch(''); setSeriesFilter('All'); }}
            className="mt-5 sort-pill sort-pill-active inline-flex"
          >
            Clear filters
          </button>
        </motion.div>
      )}
    </div>
  );
}
