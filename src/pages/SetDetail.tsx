import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Grid, LayoutList, ChevronLeft, ChevronRight } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import { CardItem } from '../components/CardItem';
import { CardDetailModal } from '../components/CardDetailModal';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { ProgressRing } from '../components/ProgressRing';
import { useCollectionStore } from '../store/collectionStore';
import type { PokemonCard, FilterOwned } from '../types';

export function SetDetail() {
  const { setId } = useParams<{ setId: string }>();
  const [searchParams] = useSearchParams();
  const lang = (searchParams.get('lang') as 'en' | 'ja' | 'th') ?? 'en';
  const isIntl = lang === 'ja' || lang === 'th';
  const [page, setPage] = useState(1);
  const [filterOwned, setFilterOwned] = useState<FilterOwned>('all');
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [gridSize, setGridSize] = useState<'small' | 'large'>('small');
  const PAGE_SIZE = 60;

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
    enabled: !!setId && filterOwned !== 'all',
    staleTime: 1000 * 60 * 10,
  });

  // Fetch price for the currently selected card
  const { data: selectedCardPrices } = useQuery({
    queryKey: ['prices', selectedCard?.id ?? ''],
    queryFn: () => pokemonTCGService.getPrices([selectedCard!.id]),
    enabled: !!selectedCard,
    staleTime: 1000 * 60 * 60,
  });

  const isLoading = filterOwned === 'all' ? loadingPage : loadingAll;
  const totalCards = cardsData?.totalCount ?? 0;

  const ownedInSet = useMemo(() => {
    if (!set) return 0;
    return Object.keys(owned).filter(id => id.startsWith(set.id + '-')).length;
  }, [owned, set]);

  const progress = set ? Math.round((ownedInSet / set.total) * 100) : 0;

  // When filter is active, work from the full card list; otherwise use current page
  const sourceCards = filterOwned === 'all'
    ? (cardsData?.data ?? [])
    : (allCardsData?.data ?? []);

  const filteredCards = useMemo(() => {
    if (filterOwned === 'owned') return sourceCards.filter(c => !!owned[c.id]);
    if (filterOwned === 'missing') return sourceCards.filter(c => !owned[c.id]);
    return sourceCards;
  }, [sourceCards, filterOwned, owned]);

  // Paginate filtered results client-side when a filter is active
  const displayCards = useMemo(() => {
    if (filterOwned === 'all') return filteredCards; // server-paginated
    const start = (page - 1) * PAGE_SIZE;
    return filteredCards.slice(start, start + PAGE_SIZE);
  }, [filteredCards, filterOwned, page]);

  const totalFiltered = filterOwned === 'all' ? totalCards : filteredCards.length;
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
