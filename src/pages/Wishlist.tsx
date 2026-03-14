import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { Heart, Trash2, DollarSign } from 'lucide-react';
import { pokemonTCGService, getCardMarketPrice } from '../services/pokemonTCG';
import { useCollectionStore } from '../store/collectionStore';
import { CardDetailModal } from '../components/CardDetailModal';
import type { PokemonCard, WishlistItem } from '../types';

const PRIORITY_COLORS = {
  High: '#f87171',
  Medium: '#F59E0B',
  Low: '#6b7280',
};

export function Wishlist() {
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [sortBy, setSortBy] = useState<'priority' | 'price' | 'date'>('priority');

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

  const cardMap: Record<string, PokemonCard> = {};
  cards?.forEach(c => { cardMap[c.id] = c; });

  const sortedWishlist = [...wishlist].sort((a, b) => {
    if (sortBy === 'priority') {
      const order = { High: 0, Medium: 1, Low: 2 };
      return order[a.priority] - order[b.priority];
    }
    if (sortBy === 'price') {
      const priceA = getCardMarketPrice(cardMap[a.cardId]) ?? 9999;
      const priceB = getCardMarketPrice(cardMap[b.cardId]) ?? 9999;
      return priceA - priceB;
    }
    return b.dateAdded.localeCompare(a.dateAdded);
  });

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

  return (
    <div className="space-y-6">
      {/* ── Header ───────────────────────────────────────── */}
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

      {/* ── Sort Controls ────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="page-section-label">Sort</span>
        {(['priority', 'price', 'date'] as const).map(opt => (
          <button
            key={opt}
            onClick={() => setSortBy(opt)}
            className={`sort-pill capitalize ${sortBy === opt ? 'sort-pill-active' : ''}`}
          >
            {opt}
          </button>
        ))}
      </div>

      {/* ── Wishlist Items ───────────────────────────────── */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 rounded-xl bg-white/5 shimmer" />
          ))}
        </div>
      ) : (
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
                  {/* Priority indicator bar */}
                  <div
                    className="w-0.5 h-12 rounded-full shrink-0"
                    style={{ background: PRIORITY_COLORS[item.priority] }}
                  />

                  {/* Card image */}
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

                  {/* Info */}
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

                  {/* Market Price */}
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

                  {/* Actions */}
                  <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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

      <CardDetailModal card={selectedCard} onClose={() => setSelectedCard(null)} />
    </div>
  );
}
