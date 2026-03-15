import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { Heart, Trash2, DollarSign, Grid, LayoutList, ArrowUpDown, Flame } from 'lucide-react';
import { pokemonTCGService, getCardMarketPrice } from '../services/pokemonTCG';
import { useCollectionStore } from '../store/collectionStore';
import { CardItem } from '../components/CardItem';
import { CardDetailModal } from '../components/CardDetailModal';
import { getRarityRank, TYPE_COLORS } from '../utils/cardConstants';
import type { PokemonCard, WishlistItem } from '../types';

const PRIORITY_COLORS = {
  High: '#f87171',
  Medium: '#F59E0B',
  Low: '#6b7280',
};

type SortOption = 'priority' | 'name-asc' | 'name-desc' | 'price-asc' | 'price-desc' | 'rarity-desc' | 'date';

export function Wishlist() {
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>('priority');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const wishlist = useCollectionStore(s => s.wishlist);
  const removeFromWishlist = useCollectionStore(s => s.removeFromWishlist);
  const updateWishlistItem = useCollectionStore(s => s.updateWishlistItem);
  const addCard = useCollectionStore(s => s.addCard);
  const isOwned = useCollectionStore(s => s.isOwned);

  const cardIds = wishlist.map(w => w.cardId);

  const { data: cards, isLoading } = useQuery({
    queryKey: ['wishlist-cards', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getCardsByIds(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 10,
  });

  const { data: prices = {} } = useQuery({
    queryKey: ['wishlist-prices', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getPrices(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 60,
  });

  const cardMap: Record<string, PokemonCard> = {};
  cards?.forEach(c => { cardMap[c.id] = c; });

  // Available types from wishlist cards
  const availableTypes = useMemo(() => {
    if (!cards) return [];
    const types = new Set<string>();
    cards.forEach(c => c.types?.forEach(t => types.add(t)));
    return Array.from(types).sort();
  }, [cards]);

  // Stats
  const totalMarketValue = useMemo(() => {
    return wishlist.reduce((sum, w) => {
      const card = cardMap[w.cardId];
      const price = card ? (getCardMarketPrice(card) ?? prices[w.cardId] ?? 0) : 0;
      return sum + price;
    }, 0);
  }, [wishlist, cardMap, prices]);

  const underTargetCount = useMemo(() => {
    return wishlist.filter(w => {
      if (!w.targetPrice) return false;
      const card = cardMap[w.cardId];
      const price = card ? (getCardMarketPrice(card) ?? prices[w.cardId] ?? null) : null;
      return price !== null && price <= w.targetPrice;
    }).length;
  }, [wishlist, cardMap, prices]);

  const sortedWishlist = useMemo(() => {
    let list = [...wishlist];

    // Type filter
    if (typeFilter) {
      list = list.filter(item => {
        const card = cardMap[item.cardId];
        return card?.types?.includes(typeFilter);
      });
    }

    // Sort
    list.sort((a, b) => {
      switch (sortBy) {
        case 'priority': {
          const order = { High: 0, Medium: 1, Low: 2 };
          return order[a.priority] - order[b.priority];
        }
        case 'name-asc': return (cardMap[a.cardId]?.name ?? '').localeCompare(cardMap[b.cardId]?.name ?? '');
        case 'name-desc': return (cardMap[b.cardId]?.name ?? '').localeCompare(cardMap[a.cardId]?.name ?? '');
        case 'price-asc': return (getCardMarketPrice(cardMap[a.cardId]) ?? 9999) - (getCardMarketPrice(cardMap[b.cardId]) ?? 9999);
        case 'price-desc': return (getCardMarketPrice(cardMap[b.cardId]) ?? 0) - (getCardMarketPrice(cardMap[a.cardId]) ?? 0);
        case 'rarity-desc': return getRarityRank(cardMap[b.cardId]?.rarity) - getRarityRank(cardMap[a.cardId]?.rarity);
        case 'date': return b.dateAdded.localeCompare(a.dateAdded);
        default: return 0;
      }
    });

    return list;
  }, [wishlist, sortBy, typeFilter, cardMap]);

  const totalTargetValue = wishlist.reduce((sum, w) => sum + (w.targetPrice ?? 0), 0);

  if (wishlist.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <p className="page-section-label mb-1.5">Want List</p>
          <h1 className="text-3xl font-black flex items-center gap-2.5">
            <Heart size={26} className="text-violet-400 shrink-0" fill="currentColor" />
            <span className="text-white">My </span>
            <span className="text-gradient-violet">Wishlist</span>
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
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="text-5xl mb-4 opacity-50"
          >
            💜
          </motion.div>
          <p className="text-gray-300 font-bold mb-1.5">Your want list is empty</p>
          <p className="text-gray-600 text-sm">Tap the heart icon on any card to add it</p>
        </motion.div>
      </div>
    );
  }

  const gridClass = viewMode === 'grid'
    ? 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3'
    : '';

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="page-section-label mb-1.5">Want List</p>
          <h1 className="text-3xl font-black flex items-center gap-2.5">
            <Heart size={26} className="text-violet-400 shrink-0" fill="currentColor" />
            <span className="text-white">My </span>
            <span className="text-gradient-violet">Wishlist</span>
          </h1>
        </div>
        <div className="text-right">
          <p className="text-sm font-bold text-gray-300">{wishlist.length} cards</p>
          {totalTargetValue > 0 && (
            <p className="text-xs text-violet-400/80">Target: ${totalTargetValue.toFixed(2)}</p>
          )}
        </div>
      </div>

      <div className="gradient-divider" />

      {/* Stats bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-500/8 border border-violet-500/15">
          <DollarSign size={12} className="text-violet-400" />
          <span className="text-xs text-gray-400">Market value:</span>
          <span className="text-xs font-bold text-violet-400">${totalMarketValue.toFixed(2)}</span>
        </div>
        {underTargetCount > 0 && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/8 border border-emerald-500/15">
            <span className="text-xs text-gray-400">Under target:</span>
            <span className="text-xs font-bold text-emerald-400">{underTargetCount} cards</span>
          </div>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Sort dropdown */}
        <div className="relative">
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value as SortOption)}
            className="appearance-none pl-7 pr-3 py-1.5 rounded-xl bg-[#1a1a2e] border border-white/5 text-xs text-gray-400 hover:text-white cursor-pointer focus:outline-none focus:border-violet-500/30 transition-colors"
          >
            <option value="priority">Priority</option>
            <option value="name-asc">Name A→Z</option>
            <option value="name-desc">Name Z→A</option>
            <option value="rarity-desc">Rarity ↓</option>
            <option value="price-desc">Price ↓</option>
            <option value="price-asc">Price ↑</option>
            <option value="date">Recently Added</option>
          </select>
          <ArrowUpDown size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
        </div>

        <span className="text-xs text-gray-600">{sortedWishlist.length} card{sortedWishlist.length !== 1 ? 's' : ''}</span>

        {/* View toggle */}
        <div className="flex gap-1 p-1 rounded-xl bg-[#1a1a2e] border border-white/5 ml-auto">
          <button
            onClick={() => setViewMode('grid')}
            className={`p-1.5 rounded-lg transition-colors ${viewMode === 'grid' ? 'text-violet-400 bg-violet-400/10' : 'text-gray-500'}`}
          >
            <Grid size={15} />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={`p-1.5 rounded-lg transition-colors ${viewMode === 'list' ? 'text-violet-400 bg-violet-400/10' : 'text-gray-500'}`}
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
        viewMode === 'grid' ? (
          <div className={gridClass}>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="aspect-[2.5/3.5] rounded-2xl bg-white/5 shimmer" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-20 rounded-xl bg-white/5 shimmer" />
            ))}
          </div>
        )
      ) : viewMode === 'grid' ? (
        /* Grid View */
        <AnimatePresence mode="popLayout">
          <motion.div
            key={`${sortBy}-${typeFilter}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={gridClass}
          >
            {sortedWishlist.map(item => {
              const card = cardMap[item.cardId];
              if (!card) return null;
              return (
                <div key={item.cardId} className="relative">
                  <CardItem card={card} onViewDetails={setSelectedCard} />
                  {/* Priority dot */}
                  <div
                    className="absolute top-2 left-7 z-30 w-2 h-2 rounded-full"
                    style={{ background: PRIORITY_COLORS[item.priority], boxShadow: `0 0 6px ${PRIORITY_COLORS[item.priority]}` }}
                    title={`${item.priority} priority`}
                  />
                </div>
              );
            })}
          </motion.div>
        </AnimatePresence>
      ) : (
        /* List View */
        <AnimatePresence>
          <div className="space-y-3">
            {sortedWishlist.map((item, i) => {
              const card = cardMap[item.cardId];
              const marketPrice = card ? getCardMarketPrice(card) : null;
              const priceGap = marketPrice && item.targetPrice ? marketPrice - item.targetPrice : null;
              const owned = isOwned(item.cardId);

              return (
                <motion.div
                  key={item.cardId}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -100 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ x: 3 }}
                  className="card-list-item group"
                  style={{ borderColor: `${PRIORITY_COLORS[item.priority]}20` }}
                >
                  <div
                    className="w-0.5 h-12 rounded-full shrink-0"
                    style={{ background: PRIORITY_COLORS[item.priority] }}
                  />
                  {card ? (
                    <img
                      src={card.images.small}
                      alt={card.name}
                      className="w-10 h-14 object-contain rounded-lg cursor-pointer hover:scale-110 transition-transform shrink-0"
                      onClick={() => setSelectedCard(card)}
                    />
                  ) : (
                    <div className="w-10 h-14 rounded-lg bg-white/5 shimmer shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-white truncate">
                      {card?.name ?? item.cardId}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span
                        className="text-xs font-bold px-1.5 py-0.5 rounded-full"
                        style={{
                          background: `${PRIORITY_COLORS[item.priority]}20`,
                          color: PRIORITY_COLORS[item.priority],
                        }}
                      >
                        {item.priority}
                      </span>
                      {card && (
                        <span className="text-xs text-gray-500">{card.set.name}</span>
                      )}
                    </div>
                    {item.targetPrice && (
                      <div className="flex items-center gap-1 mt-1">
                        <DollarSign size={10} className="text-gray-500" />
                        <span className="text-xs text-gray-500">Target: ${item.targetPrice.toFixed(2)}</span>
                        {priceGap !== null && (
                          <span className={`text-xs font-bold ${priceGap <= 0 ? 'text-emerald-400' : 'text-orange-400'}`}>
                            {priceGap <= 0 ? '✓ Under target!' : `$${priceGap.toFixed(2)} over`}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {marketPrice && (
                      <span className="text-sm font-bold text-emerald-400">${marketPrice.toFixed(2)}</span>
                    )}
                    <select
                      value={item.priority}
                      onChange={(e) => updateWishlistItem(item.cardId, { priority: e.target.value as WishlistItem['priority'] })}
                      className="text-xs bg-transparent text-gray-500 border-none outline-none cursor-pointer"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <option value="High">High</option>
                      <option value="Medium">Medium</option>
                      <option value="Low">Low</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                    {card && !owned && (
                      <motion.button
                        whileTap={{ scale: 0.9 }}
                        onClick={() => { addCard(item.cardId, marketPrice ?? undefined); removeFromWishlist(item.cardId); }}
                        className="p-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/30 text-emerald-400 transition-colors text-xs"
                        title="Mark as owned"
                      >
                        ✓
                      </motion.button>
                    )}
                    <motion.button
                      whileTap={{ scale: 0.9 }}
                      onClick={() => removeFromWishlist(item.cardId)}
                      className="p-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors"
                    >
                      <Trash2 size={12} />
                    </motion.button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </AnimatePresence>
      )}

      {sortedWishlist.length === 0 && !isLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16"
        >
          <p className="text-gray-400 text-sm">No cards match this filter</p>
        </motion.div>
      )}

      <CardDetailModal card={selectedCard} onClose={() => setSelectedCard(null)} />
    </div>
  );
}
