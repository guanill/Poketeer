import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, DollarSign, TrendingUp, Trash2, Package } from 'lucide-react';
import { pokemonTCGService } from '../services/pokemonTCG';
import { useCollectionStore } from '../store/collectionStore';
import { CardDetailModal } from '../components/CardDetailModal';
import { StatCard } from '../components/StatCard';
import type { PokemonCard } from '../types';

export function Collection() {
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const [sortBy, setSortBy] = useState<'name' | 'date' | 'value' | 'set'>('date');

  const owned = useCollectionStore(s => s.owned);
  const customPrices = useCollectionStore(s => s.customPrices);
  const removeCard = useCollectionStore(s => s.removeCard);
  const getTotalSpent = useCollectionStore(s => s.getTotalSpent);
  const getTotalCards = useCollectionStore(s => s.getTotalCards);
  const getUniqueCards = useCollectionStore(s => s.getUniqueCards);

  const cardIds = Object.keys(owned);

  const { data: cards, isLoading } = useQuery({
    queryKey: ['collection-cards', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getCardsByIds(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 10,
  });

  // Prices fetched from local backend (which caches from pokemontcg.io)
  const { data: prices = {} } = useQuery({
    queryKey: ['prices', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getPrices(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 60, // re-fetch prices once per hour
  });

  // API price first, then manually set custom price as fallback
  const getPrice = (cardId: string): number | null => prices[cardId] ?? customPrices[cardId] ?? null;

  const totalMarketValue = useMemo(() => {
    return cardIds.reduce((sum, id) => {
      const price = getPrice(id) ?? 0;
      return sum + price * (owned[id]?.quantity ?? 1);
    }, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prices, owned]);

  const profitLoss = totalMarketValue - getTotalSpent();

  const sortedCards = useMemo(() => {
    if (!cards) return [];
    return [...cards].sort((a, b) => {
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'set') return a.set.name.localeCompare(b.set.name);
      if (sortBy === 'value') {
        return (getPrice(b.id) ?? 0) - (getPrice(a.id) ?? 0);
      }
      // date
      const da = owned[a.id]?.dateAdded ?? '';
      const db = owned[b.id]?.dateAdded ?? '';
      return db.localeCompare(da);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, sortBy, owned, prices]);

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

  return (
    <div className="space-y-6">
      {/* ── Header ───────────────────────────────────────── */}
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

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          title="Market Value"
          value={`$${totalMarketValue.toFixed(2)}`}
          subtitle="current estimate"
          icon={<TrendingUp size={20} />}
          color="#10b981"
        />
        <StatCard
          title="Total Spent"
          value={`$${getTotalSpent().toFixed(2)}`}
          subtitle="purchase total"
          icon={<DollarSign size={20} />}
          color="#3b82f6"
        />
        <StatCard
          title="Profit/Loss"
          value={`${profitLoss >= 0 ? '+' : ''}$${profitLoss.toFixed(2)}`}
          subtitle={profitLoss >= 0 ? "in the green 📈" : "in the red 📉"}
          icon={<TrendingUp size={20} />}
          color={profitLoss >= 0 ? '#10b981' : '#ef4444'}
        />
        <StatCard
          title="Cards Owned"
          value={getTotalCards()}
          subtitle={`${getUniqueCards()} unique`}
          icon={<Package size={20} />}
          color="#8b5cf6"
        />
      </div>

      {/* ── Sort Controls ────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="page-section-label">Sort</span>
        {(['date', 'name', 'value', 'set'] as const).map(opt => (
          <button
            key={opt}
            onClick={() => setSortBy(opt)}
            className={`sort-pill capitalize ${sortBy === opt ? 'sort-pill-active' : ''}`}
          >
            {opt}
          </button>
        ))}
      </div>

      {/* ── Cards List ───────────────────────────────────── */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-white/5 shimmer" />
          ))}
        </div>
      ) : (
        <AnimatePresence>
          <div className="space-y-2">
            {sortedCards.map((card, i) => {
              const ownedCard = owned[card.id];
              const marketPrice = getPrice(card.id);
              const spent = ownedCard?.pricePaid ?? null;
              const profit = marketPrice && spent ? (marketPrice - spent) * ownedCard.quantity : null;

              return (
                <motion.div
                  key={card.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ delay: i * 0.02 }}
                  whileHover={{ x: 3 }}
                  className="card-list-item group"
                  onClick={() => setSelectedCard(card)}
                >
                  <img
                    src={card.images.small}
                    alt={card.name}
                    className="w-10 h-14 object-contain rounded-lg shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-white truncate">{card.name}</p>
                      {ownedCard?.quantity > 1 && (
                        <span className="text-xs px-1.5 py-0.5 rounded-full font-bold"
                          style={{ background: 'rgba(139,92,246,0.2)', color: '#c4b5fd' }}>
                          ×{ownedCard.quantity}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <p className="text-xs text-gray-500">{card.set.name}</p>
                      <span className="text-xs text-gray-600">#{card.number}</span>
                      {ownedCard?.condition && (
                        <span className="text-xs text-gray-600 border border-white/10 px-1.5 rounded">{ownedCard.condition}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {marketPrice && (
                      <span className="text-sm font-bold text-emerald-400">${marketPrice.toFixed(2)}</span>
                    )}
                    {spent && (
                      <span className="text-xs text-gray-500">paid ${spent.toFixed(2)}</span>
                    )}
                    {profit !== null && (
                      <span className={`text-xs font-bold ${profit >= 0 ? 'text-emerald-500' : 'text-red-400'}`}>
                        {profit >= 0 ? '+' : ''}${profit.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <motion.button
                    initial={{ opacity: 0 }}
                    whileHover={{ opacity: 1 }}
                    className="opacity-0 group-hover:opacity-100 p-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 shrink-0 transition-all"
                    onClick={(e) => { e.stopPropagation(); removeCard(card.id); }}
                  >
                    <Trash2 size={14} />
                  </motion.button>
                </motion.div>
              );
            })}
          </div>
        </AnimatePresence>
      )}

      <CardDetailModal
        card={selectedCard}
        onClose={() => setSelectedCard(null)}
        marketPrice={selectedCard ? getPrice(selectedCard.id) : null}
      />
    </div>
  );
}
