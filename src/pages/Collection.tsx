import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, Grid, LayoutList, ArrowUpDown, Flame } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import { useCollectionStore } from '../store/collectionStore';
import { CardItem } from '../components/CardItem';
import { CardDetailModal } from '../components/CardDetailModal';
import { RARITY_ORDER, TYPE_COLORS } from '../utils/cardConstants';
import type { PokemonCard } from '../types';

type SortOption = 'date' | 'name-asc' | 'name-desc' | 'set' | 'rarity-desc' | 'rarity-asc' | 'price-desc' | 'price-asc';

export function Collection() {
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>('date');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [gridSize, setGridSize] = useState<'small' | 'large'>('small');

  const owned = useCollectionStore(s => s.owned);
  const customPrices = useCollectionStore(s => s.customPrices);
  const getUniqueCards = useCollectionStore(s => s.getUniqueCards);
  const getTotalCards = useCollectionStore(s => s.getTotalCards);

  const cardIds = Object.keys(owned);

  const { data: cards, isLoading } = useQuery({
    queryKey: ['collection-cards', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getCardsByIds(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 10,
  });

  const { data: prices = {} } = useQuery({
    queryKey: ['prices', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getPrices(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 60,
  });

  const getPrice = (cardId: string): number | null => prices[cardId] ?? customPrices[cardId] ?? null;

  // Extract types from owned cards
  const availableTypes = useMemo(() => {
    if (!cards) return [];
    const types = new Set<string>();
    cards.forEach(c => c.types?.forEach(t => types.add(t)));
    return Array.from(types).sort();
  }, [cards]);

  const sortedCards = useMemo(() => {
    if (!cards) return [];
    let filtered = typeFilter
      ? cards.filter(c => c.types?.includes(typeFilter))
      : cards;

    return [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'name-asc': return a.name.localeCompare(b.name);
        case 'name-desc': return b.name.localeCompare(a.name);
        case 'set': return a.set.name.localeCompare(b.set.name) || parseInt(a.number) - parseInt(b.number);
        case 'rarity-desc': return (RARITY_ORDER[b.rarity?.toLowerCase() ?? ''] ?? 3) - (RARITY_ORDER[a.rarity?.toLowerCase() ?? ''] ?? 3);
        case 'rarity-asc': return (RARITY_ORDER[a.rarity?.toLowerCase() ?? ''] ?? 3) - (RARITY_ORDER[b.rarity?.toLowerCase() ?? ''] ?? 3);
        case 'price-desc': return (getPrice(b.id) ?? 0) - (getPrice(a.id) ?? 0);
        case 'price-asc': return (getPrice(a.id) ?? 0) - (getPrice(b.id) ?? 0);
        default: {
          // date — most recently added first
          const da = owned[a.id]?.dateAdded ?? '';
          const db = owned[b.id]?.dateAdded ?? '';
          return db.localeCompare(da);
        }
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, sortBy, owned, prices, typeFilter]);

  // Group by set when sorting by set
  const groupedBySet = useMemo(() => {
    if (sortBy !== 'set') return null;
    const groups: { name: string; logo?: string; cards: PokemonCard[] }[] = [];
    let current: typeof groups[0] | null = null;
    for (const card of sortedCards) {
      if (!current || current.name !== card.set.name) {
        current = { name: card.set.name, logo: card.set.images.logo, cards: [] };
        groups.push(current);
      }
      current.cards.push(card);
    }
    return groups;
  }, [sortBy, sortedCards]);

  if (cardIds.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <p className="page-section-label mb-1.5">Card Vault</p>
          <h1 className="text-3xl font-black flex items-center gap-2.5">
            <BookOpen size={26} className="text-amber-400 shrink-0" />
            <span className="text-white">My </span>
            <span className="text-gradient-gold">Collection</span>
          </h1>
        </div>
        <div className="gradient-divider" />
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center py-24 rounded-2xl"
          style={{
            background: 'linear-gradient(145deg, #111128, #0d0d20)',
            border: '1px solid rgba(139,92,246,0.12)',
          }}
        >
          <motion.div
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="text-5xl mb-4 opacity-60"
          >
            📦
          </motion.div>
          <p className="text-gray-300 font-bold mb-1.5">Your vault is empty</p>
          <p className="text-gray-600 text-sm">Browse sets and add cards to get started</p>
        </motion.div>
      </div>
    );
  }

  const gridClass = gridSize === 'small'
    ? 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3'
    : 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4';

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="page-section-label mb-1.5">Card Vault</p>
          <h1 className="text-3xl font-black flex items-center gap-2.5">
            <BookOpen size={26} className="text-amber-400 shrink-0" />
            <span className="text-white">My </span>
            <span className="text-gradient-gold">Collection</span>
          </h1>
        </div>
        <div className="text-right">
          <p className="text-sm font-bold text-gray-300">{getUniqueCards()} unique</p>
          <p className="text-xs text-gray-600">{getTotalCards()} total cards</p>
        </div>
      </div>

      <div className="gradient-divider" />

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Sort dropdown */}
        <div className="relative">
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value as SortOption)}
            className="appearance-none pl-7 pr-3 py-1.5 rounded-xl bg-[#1a1a2e] border border-white/5 text-xs text-gray-400 hover:text-white cursor-pointer focus:outline-none focus:border-violet-500/30 transition-colors"
          >
            <option value="date">Recently Added</option>
            <option value="name-asc">Name A→Z</option>
            <option value="name-desc">Name Z→A</option>
            <option value="set">By Set</option>
            <option value="rarity-desc">Rarity ↓</option>
            <option value="rarity-asc">Rarity ↑</option>
            <option value="price-desc">Price ↓</option>
            <option value="price-asc">Price ↑</option>
          </select>
          <ArrowUpDown size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        </div>

        {/* Results count */}
        <span className="text-xs text-gray-600">
          {sortedCards.length} card{sortedCards.length !== 1 ? 's' : ''}
        </span>

        {/* Grid toggle */}
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

      {/* Type filter chips */}
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

      {/* Cards */}
      {isLoading ? (
        <div className={gridClass}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="aspect-[2.5/3.5] rounded-2xl bg-white/5 shimmer" />
          ))}
        </div>
      ) : groupedBySet ? (
        // Grouped by set view
        <div className="space-y-6">
          {groupedBySet.map(group => (
            <div key={group.name}>
              <div className="flex items-center gap-3 mb-3">
                {group.logo && (
                  <img src={group.logo} alt={group.name} className="h-6 object-contain" />
                )}
                <h3 className="text-sm font-bold text-gray-400">{group.name}</h3>
                <span className="text-xs text-gray-600">{group.cards.length} cards</span>
              </div>
              <AnimatePresence mode="popLayout">
                <motion.div className={gridClass}>
                  {group.cards.map(card => (
                    <CardItem key={card.id} card={card} onViewDetails={setSelectedCard} />
                  ))}
                </motion.div>
              </AnimatePresence>
            </div>
          ))}
        </div>
      ) : (
        // Flat grid view
        <AnimatePresence mode="popLayout">
          <motion.div
            key={`${sortBy}-${typeFilter}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={gridClass}
          >
            {sortedCards.map(card => (
              <CardItem key={card.id} card={card} onViewDetails={setSelectedCard} />
            ))}
          </motion.div>
        </AnimatePresence>
      )}

      {sortedCards.length === 0 && !isLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16"
        >
          <p className="text-gray-400 text-sm">No cards match this filter</p>
        </motion.div>
      )}

      <CardDetailModal
        card={selectedCard}
        onClose={() => setSelectedCard(null)}
        marketPrice={selectedCard ? getPrice(selectedCard.id) : null}
      />
    </div>
  );
}
