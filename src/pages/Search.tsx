import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Search as SearchIcon, X, Sparkles, Loader2 } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import { CardItem } from '../components/CardItem';
import { CardDetailModal } from '../components/CardDetailModal';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import type { PokemonCard } from '../types';

const POPULAR_SEARCHES = [
  'Charizard', 'Pikachu', 'Mewtwo', 'Eevee', 'Rayquaza',
  'Lugia', 'Gengar', 'Blaziken', 'Umbreon', 'Snorlax',
];

const PAGE_SIZE = 30;

export function Search() {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [debounceTimeout, setDebounceTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const handleInput = (value: string) => {
    setQuery(value);
    if (debounceTimeout) clearTimeout(debounceTimeout);
    const t = setTimeout(() => setDebouncedQuery(value), 150);
    setDebounceTimeout(t);
  };

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
      // totalCount === -1 means "there are more"
      if (lastPage.totalCount === -1) return lastPage.page + 1;
      // If we got fewer than pageSize, we're done
      if (lastPage.count < PAGE_SIZE) return undefined;
      return undefined;
    },
    enabled: debouncedQuery.length >= 2,
    staleTime: 1000 * 60 * 5,
  });

  const allCards = data?.pages.flatMap((p) => p.data) ?? [];

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
    if (lastPage.totalCount === -1) {
      // We know there are more
      return (
        <>
          <span className="text-amber-400/80 font-bold">{allCards.length}+</span> results for{' '}
          <span className="text-white font-bold">"{debouncedQuery}"</span>
        </>
      );
    }
    return (
      <>
        <span className="text-amber-400/80 font-bold">{allCards.length}</span> results for{' '}
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

      {/* Results */}
      <AnimatePresence mode="wait">
        {isLoading && debouncedQuery ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <LoadingSkeleton count={12} type="card" />
          </motion.div>
        ) : allCards.length > 0 ? (
          <motion.div
            key="results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <p className="text-sm text-gray-500 mb-4">{resultText}</p>
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
              {allCards.map((card) => (
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
