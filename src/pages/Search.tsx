import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Search as SearchIcon, X, Sparkles, Loader2, ArrowUpDown, Flame } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import { CardItem } from '../components/CardItem';
import { CardDetailModal } from '../components/CardDetailModal';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { getRarityRank, TYPE_COLORS } from '../utils/cardConstants';
import type { PokemonCard } from '../types';

const POPULAR_SEARCHES = [
  'Charizard', 'Pikachu', 'Mewtwo', 'Eevee', 'Rayquaza',
  'Lugia', 'Gengar', 'Blaziken', 'Umbreon', 'Snorlax',
];

const PAGE_SIZE = 30;

type SortOption = 'relevance' | 'name-asc' | 'name-desc' | 'rarity-desc' | 'rarity-asc';

export function Search() {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [debounceTimeout, setDebounceTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>('relevance');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const handleInput = (value: string) => {
    setQuery(value);
    if (debounceTimeout) clearTimeout(debounceTimeout);
    const t = setTimeout(() => setDebouncedQuery(value), 150);
    setDebounceTimeout(t);
  };

  // Reset filters when query changes
  useEffect(() => {
    setSortBy('relevance');
    setTypeFilter(null);
  }, [debouncedQuery]);

  const {
    data,
    isLoading,
    isFetching,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
  } = useInfiniteQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: ({ pageParam = 1 }) =>
      pokemonTCGService.searchCards(debouncedQuery, pageParam, PAGE_SIZE),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      if (lastPage.totalCount === -1) return lastPage.page + 1;
      if (lastPage.count < PAGE_SIZE) return undefined;
      return undefined;
    },
    enabled: debouncedQuery.length >= 2,
    staleTime: 1000 * 60 * 5,
  });

  const allCards = data?.pages.flatMap((p) => p.data) ?? [];

  // Extract types from loaded results
  const availableTypes = useMemo(() => {
    const types = new Set<string>();
    allCards.forEach(c => c.types?.forEach(t => types.add(t)));
    return Array.from(types).sort();
  }, [allCards]);

  // Apply client-side filtering and sorting
  const displayCards = useMemo(() => {
    let cards = allCards;
    if (typeFilter) {
      cards = cards.filter(c => c.types?.includes(typeFilter));
    }
    if (sortBy !== 'relevance') {
      cards = [...cards].sort((a, b) => {
        switch (sortBy) {
          case 'name-asc': return a.name.localeCompare(b.name);
          case 'name-desc': return b.name.localeCompare(a.name);
          case 'rarity-desc': return getRarityRank(b.rarity) - getRarityRank(a.rarity);
          case 'rarity-asc': return getRarityRank(a.rarity) - getRarityRank(b.rarity);
          default: return 0;
        }
      });
    }
    return cards;
  }, [allCards, sortBy, typeFilter]);

  // Infinite scroll observer
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const target = entries[0];
      if (target.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage],
  );

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(handleObserver, { threshold: 0.1 });
    observer.observe(el);
    return () => observer.disconnect();
  }, [handleObserver]);

  // Build result count text
  const resultText = (() => {
    if (!data || allCards.length === 0) return null;
    const lastPage = data.pages[data.pages.length - 1];
    const countLabel = displayCards.length !== allCards.length
      ? `${displayCards.length} of ${allCards.length}`
      : lastPage.totalCount === -1
      ? `${allCards.length}+`
      : `${allCards.length}`;

    return (
      <>
        <span className="text-amber-400/80 font-bold">{countLabel}</span> results for{' '}
        <span className="text-white font-bold">"{debouncedQuery}"</span>
      </>
    );
  })();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <p className="page-section-label mb-1.5">Card Database</p>
        <h1 className="text-3xl font-black flex items-center gap-2.5">
          <SearchIcon size={26} className="text-amber-400 shrink-0" />
          <span className="text-white">Search </span>
          <span className="text-gradient-gold">Cards</span>
        </h1>
        <p className="text-sm text-gray-500 mt-1">Search across all TCG card releases</p>
      </div>

      <div className="gradient-divider" />

      {/* Search Input */}
      <div className="relative">
        <SearchIcon size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        <input
          type="text"
          placeholder="Search by card name..."
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          autoFocus
          className="tcg-input w-full pl-12 pr-12 py-4 text-base"
        />
        {query && !isFetching && (
          <button
            onClick={() => { setQuery(''); setDebouncedQuery(''); }}
            className="absolute right-4 top-1/2 -translate-y-1/2 p-1 rounded-lg text-gray-500 hover:text-white transition-colors"
          >
            <X size={16} />
          </button>
        )}
        {isFetching && !isFetchingNextPage && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
              className="w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full"
            />
          </div>
        )}
      </div>

      {/* Popular Searches */}
      {!debouncedQuery && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={13} className="text-amber-400" />
            <span className="page-section-label">Popular</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {POPULAR_SEARCHES.map((name, i) => (
              <motion.button
                key={name}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.04 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => { setQuery(name); setDebouncedQuery(name); }}
                className="series-badge"
              >
                {name}
              </motion.button>
            ))}
          </div>
        </motion.div>
      )}

      {/* Sort & Filter toolbar — only show when we have results */}
      {allCards.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value as SortOption)}
                className="appearance-none pl-7 pr-3 py-1.5 rounded-xl bg-[#1a1a2e] border border-white/5 text-xs text-gray-400 hover:text-white cursor-pointer focus:outline-none focus:border-violet-500/30 transition-colors"
              >
                <option value="relevance">Relevance</option>
                <option value="name-asc">Name A→Z</option>
                <option value="name-desc">Name Z→A</option>
                <option value="rarity-desc">Rarity ↓</option>
                <option value="rarity-asc">Rarity ↑</option>
              </select>
              <ArrowUpDown size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
            </div>
            <span className="text-xs text-gray-600">{resultText}</span>
          </div>

          {availableTypes.length > 1 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Flame size={13} className="text-gray-600 shrink-0" />
              <button
                onClick={() => setTypeFilter(null)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors ${
                  !typeFilter
                    ? 'bg-white/10 text-white border border-white/15'
                    : 'text-gray-500 hover:text-gray-300 border border-transparent'
                }`}
              >
                All
              </button>
              {availableTypes.map(t => {
                const tc = TYPE_COLORS[t] ?? { color: '#9ca3af', bg: 'rgba(156,163,175,0.15)' };
                const active = typeFilter === t;
                return (
                  <button
                    key={t}
                    onClick={() => setTypeFilter(active ? null : t)}
                    className="px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all"
                    style={{
                      background: active ? tc.bg : 'transparent',
                      color: active ? tc.color : '#6b7280',
                      border: active ? `1px solid ${tc.color}40` : '1px solid transparent',
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Results */}
      <AnimatePresence mode="wait">
        {isLoading && debouncedQuery ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <LoadingSkeleton count={12} type="card" />
          </motion.div>
        ) : displayCards.length > 0 ? (
          <motion.div
            key="results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
              {displayCards.map((card) => (
                <CardItem key={card.id} card={card} onViewDetails={setSelectedCard} />
              ))}
            </div>

            {/* Infinite scroll sentinel */}
            <div ref={sentinelRef} className="h-4" />

            {isFetchingNextPage && (
              <div className="flex justify-center py-6">
                <Loader2 size={24} className="animate-spin text-amber-400/60" />
              </div>
            )}
          </motion.div>
        ) : debouncedQuery.length >= 2 && !isLoading ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-20 rounded-2xl"
            style={{
              background: 'linear-gradient(145deg, #111128, #0d0d20)',
              border: '1px solid rgba(139,92,246,0.1)',
            }}
          >
            <div className="text-5xl mb-4 opacity-40">&#x1F0CF;</div>
            <p className="text-gray-400 font-semibold">No cards found for "{debouncedQuery}"</p>
            <p className="text-gray-600 text-sm mt-1">Try a different name</p>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <CardDetailModal card={selectedCard} onClose={() => setSelectedCard(null)} />
    </div>
  );
}
