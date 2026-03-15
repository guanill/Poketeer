import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Grid, LayoutList, ChevronLeft, ChevronRight, ArrowUpDown, Flame } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import { CardItem } from '../components/CardItem';
import { CardDetailModal } from '../components/CardDetailModal';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { ProgressRing } from '../components/ProgressRing';
import { useCollectionStore } from '../store/collectionStore';
import { getCardMarketPrice } from '../services/pokemonTCG';
import { getRarityRank, TYPE_COLORS } from '../utils/cardConstants';
import type { PokemonCard, FilterOwned } from '../types';

type SortOption = 'number' | 'name-asc' | 'name-desc' | 'rarity-asc' | 'rarity-desc' | 'price-desc' | 'price-asc';

export function SetDetail() {
  const { setId } = useParams<{ setId: string }>();
  const [searchParams] = useSearchParams();
  const lang = (searchParams.get('lang') as 'en' | 'ja' | 'th') ?? 'en';
  const isIntl = lang === 'ja' || lang === 'th';
  const [page, setPage] = useState(1);
  const [filterOwned, setFilterOwned] = useState<FilterOwned>('all');
  const [sortBy, setSortBy] = useState<SortOption>('number');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [gridSize, setGridSize] = useState<'small' | 'large'>('small');
  const PAGE_SIZE = 60;

  const hasActiveFilters = sortBy !== 'number' || typeFilter !== null;

  const owned = useCollectionStore(s => s.owned);

  const { data: set } = useQuery({
    queryKey: ['set', setId, lang],
    queryFn: () => pokemonTCGService.getSet(setId!, lang),
    enabled: !!setId,
    staleTime: 1000 * 60 * 60,
  });

  // Paginated query — used for "All" view
  const { data: cardsData, isLoading: loadingPage } = useQuery({
    queryKey: ['cards', setId, page, lang],
    queryFn: () => isIntl
      ? pokemonTCGService.getIntlCardsBySet(lang as 'ja' | 'th', setId!, page, PAGE_SIZE)
      : pokemonTCGService.getCardsBySet(setId!, page, PAGE_SIZE),
    enabled: !!setId,
    staleTime: 1000 * 60 * 10,
  });

  // Full-set query — fetches every card once, used when a filter is active
  const { data: allCardsData, isLoading: loadingAll } = useQuery({
    queryKey: ['cards-all', setId, lang],
    queryFn: () => isIntl
      ? pokemonTCGService.getIntlCardsBySet(lang as 'ja' | 'th', setId!, 1, 500)
      : pokemonTCGService.getCardsBySet(setId!, 1, 500),
    enabled: !!setId && (filterOwned !== 'all' || hasActiveFilters),
    staleTime: 1000 * 60 * 10,
  });

  // Fetch price for the currently selected card
  const { data: selectedCardPrices } = useQuery({
    queryKey: ['prices', selectedCard?.id ?? ''],
    queryFn: () => pokemonTCGService.getPrices([selectedCard!.id]),
    enabled: !!selectedCard,
    staleTime: 1000 * 60 * 60,
  });

  // When filter/sort is active, work from the full card list; otherwise use current page
  const needsAllCards = filterOwned !== 'all' || hasActiveFilters;

  const isLoading = needsAllCards ? loadingAll : loadingPage;
  const totalCards = cardsData?.totalCount ?? 0;

  const ownedInSet = useMemo(() => {
    if (!set) return 0;
    return Object.keys(owned).filter(id => id.startsWith(set.id + '-')).length;
  }, [owned, set]);

  const progress = set ? Math.round((ownedInSet / set.total) * 100) : 0;
  const sourceCards = needsAllCards
    ? (allCardsData?.data ?? [])
    : (cardsData?.data ?? []);

  // Extract unique types for the filter buttons
  const availableTypes = useMemo(() => {
    const cards = allCardsData?.data ?? cardsData?.data ?? [];
    const types = new Set<string>();
    cards.forEach(c => c.types?.forEach(t => types.add(t)));
    return Array.from(types).sort();
  }, [allCardsData, cardsData]);

  const filteredCards = useMemo(() => {
    let cards = sourceCards;

    // Ownership filter
    if (filterOwned === 'owned') cards = cards.filter(c => !!owned[c.id]);
    else if (filterOwned === 'missing') cards = cards.filter(c => !owned[c.id]);

    // Type filter
    if (typeFilter) cards = cards.filter(c => c.types?.includes(typeFilter));

    // Sorting
    if (sortBy !== 'number') {
      cards = [...cards].sort((a, b) => {
        switch (sortBy) {
          case 'name-asc': return a.name.localeCompare(b.name);
          case 'name-desc': return b.name.localeCompare(a.name);
          case 'rarity-asc': return getRarityRank(a.rarity) - getRarityRank(b.rarity);
          case 'rarity-desc': return getRarityRank(b.rarity) - getRarityRank(a.rarity);
          case 'price-desc': return (getCardMarketPrice(b) ?? 0) - (getCardMarketPrice(a) ?? 0);
          case 'price-asc': return (getCardMarketPrice(a) ?? 0) - (getCardMarketPrice(b) ?? 0);
          default: return 0;
        }
      });
    }

    return cards;
  }, [sourceCards, filterOwned, owned, typeFilter, sortBy]);

  // Paginate filtered results client-side when filters/sort are active
  const displayCards = useMemo(() => {
    if (!needsAllCards) return filteredCards; // server-paginated
    const start = (page - 1) * PAGE_SIZE;
    return filteredCards.slice(start, start + PAGE_SIZE);
  }, [filteredCards, needsAllCards, page]);

  const totalFiltered = !needsAllCards ? totalCards : filteredCards.length;
  const totalPages = Math.ceil(totalFiltered / PAGE_SIZE);

  // Reset to page 1 whenever filter changes
  const handleFilterChange = (f: FilterOwned) => {
    setFilterOwned(f);
    setPage(1);
  };

  const getProgressColor = () => {
    if (progress === 100) return '#F59E0B';
    if (progress >= 75) return '#10b981';
    if (progress >= 50) return '#3b82f6';
    return '#6b7280';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link to={isIntl ? `/sets?lang=${lang}` : '/sets'}>
          <motion.button
            whileHover={{ x: -2 }}
            whileTap={{ scale: 0.95 }}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors mt-1"
          >
            <ArrowLeft size={18} />
          </motion.button>
        </Link>

        <div className="flex-1 min-w-0">
          <p className="page-section-label mb-1">Set Detail</p>
          <div className="flex items-center gap-3 flex-wrap">
            {set?.images.logo && (
              <motion.img
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                src={set.images.logo}
                alt={set?.name}
                className="h-12 object-contain"
              />
            )}
            <div>
              <h1 className="text-2xl font-black text-white">{set?.name ?? 'Loading...'}</h1>
              <p className="text-sm text-gray-500">{set?.series} · {set?.releaseDate}</p>
            </div>
          </div>
        </div>

        {/* Progress Ring */}
        <div className="shrink-0 flex flex-col items-center gap-1">
          <ProgressRing progress={progress} size={64} strokeWidth={5} color={getProgressColor()}>
            <span className="text-sm font-black" style={{ color: getProgressColor() }}>{progress}%</span>
          </ProgressRing>
          <p className="text-xs text-gray-500">{ownedInSet}/{set?.total ?? '?'}</p>
          {progress === 100 && (
            <motion.span
              animate={{ scale: [1, 1.2, 1] }}
              transition={{ repeat: Infinity, duration: 1.5 }}
              className="text-amber-400 text-sm"
            >
              ✨
            </motion.span>
          )}
        </div>
      </div>

      <div className="gradient-divider" />

      {/* Toolbar row 1: Ownership filter + grid toggle */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex gap-1 p-1 rounded-xl bg-[#1a1a2e] border border-white/5">
          {(['all', 'owned', 'missing'] as const).map(f => (
            <button
              key={f}
              onClick={() => handleFilterChange(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize ${
                filterOwned === f
                  ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {f === 'all'
                ? `All (${totalCards})`
                : f === 'owned'
                ? `Owned (${ownedInSet})`
                : `Missing (${Math.max(0, totalCards - ownedInSet)})`}
            </button>
          ))}
        </div>

        {/* Sort dropdown */}
        <div className="relative">
          <select
            value={sortBy}
            onChange={e => { setSortBy(e.target.value as SortOption); setPage(1); }}
            className="appearance-none pl-7 pr-3 py-1.5 rounded-xl bg-[#1a1a2e] border border-white/5 text-xs text-gray-400 hover:text-white cursor-pointer focus:outline-none focus:border-violet-500/30 transition-colors"
          >
            <option value="number"># Number</option>
            <option value="name-asc">Name A→Z</option>
            <option value="name-desc">Name Z→A</option>
            <option value="rarity-desc">Rarity ↓</option>
            <option value="rarity-asc">Rarity ↑</option>
            <option value="price-desc">Price ↓</option>
            <option value="price-asc">Price ↑</option>
          </select>
          <ArrowUpDown size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        </div>

        <div className="flex gap-1 p-1 rounded-xl bg-[#1a1a2e] border border-white/5 ml-auto">
          <button
            onClick={() => setGridSize('small')}
            className={`p-1.5 rounded-lg transition-colors ${gridSize === 'small' ? 'text-amber-400 bg-amber-400/10' : 'text-gray-500'}`}
          >
            <Grid size={15} />
          </button>
          <button
            onClick={() => setGridSize('large')}
            className={`p-1.5 rounded-lg transition-colors ${gridSize === 'large' ? 'text-amber-400 bg-amber-400/10' : 'text-gray-500'}`}
          >
            <LayoutList size={15} />
          </button>
        </div>
      </div>

      {/* Toolbar row 2: Type filter chips */}
      {availableTypes.length > 1 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <Flame size={13} className="text-gray-600 shrink-0" />
          <button
            onClick={() => { setTypeFilter(null); setPage(1); }}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors ${
              !typeFilter
                ? 'bg-white/10 text-white border border-white/15'
                : 'text-gray-500 hover:text-gray-300 border border-transparent'
            }`}
          >
            All Types
          </button>
          {availableTypes.map(t => {
            const tc = TYPE_COLORS[t] ?? { color: '#9ca3af', bg: 'rgba(156,163,175,0.15)' };
            const active = typeFilter === t;
            return (
              <button
                key={t}
                onClick={() => { setTypeFilter(active ? null : t); setPage(1); }}
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

      {/* Card Grid */}
      {isLoading ? (
        <LoadingSkeleton count={24} type="card" />
      ) : (
        <AnimatePresence mode="popLayout">
          <motion.div
            key={`${page}-${filterOwned}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={
              gridSize === 'small'
                ? 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3'
                : 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4'
            }
          >
            {displayCards.map((card) => (
              <CardItem
                key={card.id}
                card={card}
                onViewDetails={setSelectedCard}
              />
            ))}
          </motion.div>
        </AnimatePresence>
      )}

      {displayCards.length === 0 && !isLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16"
        >
          <p className="text-4xl mb-3">🎉</p>
          <p className="text-gray-400 text-sm">
            {filterOwned === 'owned' ? 'No cards owned yet' : 'All cards collected!'}
          </p>
        </motion.div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-4">
          <motion.button
            whileTap={{ scale: 0.9 }}
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
            className="p-2 rounded-xl bg-[#1a1a2e] border border-white/10 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft size={18} />
          </motion.button>
          <span className="text-sm text-gray-400">
            Page {page} of {totalPages}
          </span>
          <motion.button
            whileTap={{ scale: 0.9 }}
            disabled={page === totalPages}
            onClick={() => setPage(p => p + 1)}
            className="p-2 rounded-xl bg-[#1a1a2e] border border-white/10 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight size={18} />
          </motion.button>
        </div>
      )}

      {/* Card Detail Modal */}
      <CardDetailModal
        card={selectedCard}
        onClose={() => setSelectedCard(null)}
        marketPrice={selectedCard && selectedCardPrices ? (selectedCardPrices[selectedCard.id] ?? null) : null}
      />
    </div>
  );
}
