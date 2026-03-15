import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  Package, Heart, Layers, DollarSign,
  Trophy, BarChart3, ChevronRight, TrendingUp
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { pokemonTCGService, getRarityColor } from '../services/pokemonTCG';
import { useCollectionStore } from '../store/collectionStore';
import { StatCard } from '../components/StatCard';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { TYPE_COLORS } from '../utils/cardConstants';

export function Dashboard() {
  const owned = useCollectionStore(s => s.owned);
  const wishlist = useCollectionStore(s => s.wishlist);
  const getTotalSpent = useCollectionStore(s => s.getTotalSpent);
  const getTotalCards = useCollectionStore(s => s.getTotalCards);
  const getUniqueCards = useCollectionStore(s => s.getUniqueCards);

  const cardIds = Object.keys(owned);

  const { data: sets, isLoading } = useQuery({
    queryKey: ['sets', 'v2', 'en'],
    queryFn: () => pokemonTCGService.getSets('en'),
    staleTime: 1000 * 60 * 60,
  });

  // Prices for portfolio value
  const { data: prices = {} } = useQuery({
    queryKey: ['dashboard-prices', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getPrices(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 60,
  });

  // Card details for insights
  const { data: ownedCards } = useQuery({
    queryKey: ['dashboard-owned-cards', cardIds.join(',')],
    queryFn: () => pokemonTCGService.getCardsByIds(cardIds),
    enabled: cardIds.length > 0,
    staleTime: 1000 * 60 * 10,
  });

  // Compute set progress
  const setProgress = useMemo(() => {
    if (!sets) return [];
    const ownedBySet: Record<string, number> = {};
    Object.keys(owned).forEach(cardId => {
      const parts = cardId.split('-');
      const setId = parts.length >= 2 ? parts.slice(0, parts.length - 1).join('-') : parts[0];
      ownedBySet[setId] = (ownedBySet[setId] ?? 0) + 1;
    });

    return sets
      .filter(s => ownedBySet[s.id] > 0)
      .map(s => ({
        set: s,
        owned: ownedBySet[s.id] ?? 0,
        progress: Math.round(((ownedBySet[s.id] ?? 0) / s.total) * 100),
      }))
      .sort((a, b) => b.progress - a.progress)
      .slice(0, 5);
  }, [sets, owned]);

  const totalSpent = getTotalSpent();
  const totalCards = getTotalCards();
  const uniqueCards = getUniqueCards();
  const completeSets = setProgress.filter(s => s.progress === 100).length;

  // Portfolio value
  const marketValue = useMemo(() => {
    return cardIds.reduce((sum, id) => {
      const price = prices[id] ?? 0;
      return sum + price * (owned[id]?.quantity ?? 1);
    }, 0);
  }, [prices, owned, cardIds]);

  const profitLoss = marketValue - totalSpent;

  // Collection insights
  const rarityDistribution = useMemo(() => {
    if (!ownedCards) return [];
    const counts: Record<string, number> = {};
    ownedCards.forEach(c => {
      const r = c.rarity ?? 'Common';
      counts[r] = (counts[r] ?? 0) + (owned[c.id]?.quantity ?? 1);
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [ownedCards, owned]);

  const typeDistribution = useMemo(() => {
    if (!ownedCards) return [];
    const counts: Record<string, number> = {};
    ownedCards.forEach(c => {
      c.types?.forEach(t => {
        counts[t] = (counts[t] ?? 0) + (owned[c.id]?.quantity ?? 1);
      });
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [ownedCards, owned]);

  const maxRarityCount = rarityDistribution[0]?.[1] ?? 1;
  const maxTypeCount = typeDistribution[0]?.[1] ?? 1;

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-8"
    >
      {/* Hero */}
      <motion.div
        variants={itemVariants}
        className="relative rounded-2xl overflow-hidden p-6 md:p-8"
        style={{
          background: 'linear-gradient(135deg, #0d0820 0%, #0f0f2a 45%, #061428 100%)',
          border: '1px solid rgba(139,92,246,0.2)',
          boxShadow: '0 8px 40px rgba(139,92,246,0.07), inset 0 1px 0 rgba(255,255,255,0.04)',
        }}
      >
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div
            className="absolute -right-24 -top-24 w-72 h-72 rounded-full"
            style={{ border: '28px solid rgba(139,92,246,0.07)' }}
          />
          <div
            className="absolute -right-12 -top-12 w-48 h-48 rounded-full"
            style={{ border: '8px solid rgba(139,92,246,0.05)' }}
          />
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 30, repeat: Infinity, ease: 'linear' }}
            className="absolute -bottom-24 -left-24 w-72 h-72 rounded-full"
            style={{ border: '20px solid rgba(59,130,246,0.07)' }}
          />
          <motion.div
            animate={{ scale: [1, 1.3, 1], opacity: [0.05, 0.12, 0.05] }}
            transition={{ duration: 6, repeat: Infinity }}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-32"
            style={{ background: 'radial-gradient(ellipse, rgba(139,92,246,0.1), transparent 70%)' }}
          />
        </div>

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-3">
            <motion.div
              animate={{ y: [0, -4, 0] }}
              transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
            >
              <svg width="40" height="52" viewBox="0 0 40 52" fill="none" xmlns="http://www.w3.org/2000/svg"
                style={{ filter: 'drop-shadow(0 0 10px rgba(139,92,246,0.7))' }}
              >
                <rect x="2" y="2" width="36" height="48" rx="4" fill="#1a1040"
                  stroke="url(#heroBorder)" strokeWidth="2" />
                <rect x="5" y="5" width="30" height="42" rx="2.5"
                  fill="none" stroke="rgba(245,158,11,0.35)" strokeWidth="1" />
                <rect x="7" y="8" width="26" height="18" rx="2" fill="url(#heroArt)" />
                <path d="M9 10 L20 8 L21 26 L8 22 Z" fill="rgba(255,255,255,0.09)" />
                <path d="M20 13 L21.4 17 L25 18 L21.4 19 L20 23 L18.6 19 L15 18 L18.6 17 Z"
                  fill="#F59E0B" opacity="0.95" />
                <path d="M20 14.5 L20.9 17 L23 18 L20.9 19 L20 21.5 L19.1 19 L17 18 L19.1 17 Z"
                  fill="rgba(255,255,255,0.3)" />
                <rect x="7" y="28" width="18" height="3" rx="1.5" fill="rgba(245,158,11,0.5)" />
                <rect x="7" y="33" width="26" height="2" rx="1" fill="rgba(255,255,255,0.12)" />
                <rect x="7" y="37" width="20" height="2" rx="1" fill="rgba(255,255,255,0.08)" />
                <circle cx="29" cy="43" r="2" fill="#8B5CF6" opacity="0.7" />
                <circle cx="24" cy="43" r="2" fill="#3b82f6" opacity="0.5" />
                <circle cx="32" cy="10" r="1.5" fill="rgba(255,255,255,0.6)" />
                <line x1="32" y1="7.5" x2="32" y2="12.5" stroke="rgba(255,255,255,0.4)" strokeWidth="0.8" />
                <line x1="29.5" y1="10" x2="34.5" y2="10" stroke="rgba(255,255,255,0.4)" strokeWidth="0.8" />
                <defs>
                  <linearGradient id="heroBorder" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#8B5CF6" />
                    <stop offset="50%" stopColor="#F59E0B" />
                    <stop offset="100%" stopColor="#3b82f6" />
                  </linearGradient>
                  <linearGradient id="heroArt" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#2d1b69" />
                    <stop offset="100%" stopColor="#1e3a5f" />
                  </linearGradient>
                </defs>
              </svg>
            </motion.div>
            <div>
              <h1 className="text-2xl md:text-3xl font-black text-white">
                {uniqueCards === 0 ? 'Start Your Journey' : 'Your Collection'}
              </h1>
              <p className="text-sm text-gray-400 font-semibold">
                {uniqueCards === 0
                  ? 'Browse sets and add your first card!'
                  : `Tracking ${uniqueCards} unique cards across ${sets?.length ?? 0} sets`}
              </p>
            </div>
          </div>

          {uniqueCards === 0 && (
            <Link to="/sets">
              <motion.button
                whileHover={{ scale: 1.04, boxShadow: '0 0 20px rgba(255,203,5,0.4)' }}
                whileTap={{ scale: 0.97 }}
                className="mt-4 px-6 py-3 rounded-xl font-black text-black text-sm flex items-center gap-2"
                style={{ background: 'linear-gradient(135deg, #F59E0B, #d97706)' }}
              >
                <Layers size={16} />
                Browse All Sets
              </motion.button>
            </Link>
          )}
        </div>
      </motion.div>

      {/* Stats Grid */}
      <motion.div variants={itemVariants} className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <StatCard
          title="Total Cards"
          value={totalCards}
          subtitle={`${uniqueCards} unique`}
          icon={<Package size={20} />}
          color="#3b82f6"
          delay={0}
        />
        <StatCard
          title="Market Value"
          value={`$${marketValue.toFixed(2)}`}
          subtitle="current portfolio"
          icon={<TrendingUp size={20} />}
          color="#8b5cf6"
          delay={0.05}
        />
        <StatCard
          title="Profit / Loss"
          value={`${profitLoss >= 0 ? '+' : ''}$${profitLoss.toFixed(2)}`}
          subtitle={totalSpent > 0 ? `spent $${totalSpent.toFixed(2)}` : 'no purchases tracked'}
          icon={<DollarSign size={20} />}
          color={profitLoss >= 0 ? '#10b981' : '#ef4444'}
          delay={0.1}
        />
        <StatCard
          title="Complete Sets"
          value={completeSets}
          subtitle="100% finished"
          icon={<Trophy size={20} />}
          color="#F59E0B"
          delay={0.15}
        />
        <StatCard
          title="Wishlist"
          value={wishlist.length}
          subtitle="cards wanted"
          icon={<Heart size={20} />}
          color="#ec4899"
          delay={0.2}
        />
        <StatCard
          title="Total Spent"
          value={`$${totalSpent.toFixed(2)}`}
          subtitle="purchase total"
          icon={<DollarSign size={20} />}
          color="#10b981"
          delay={0.25}
        />
      </motion.div>

      {/* Collection Insights */}
      {uniqueCards > 0 && ownedCards && (rarityDistribution.length > 0 || typeDistribution.length > 0) && (
        <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Rarity Breakdown */}
          {rarityDistribution.length > 0 && (
            <div
              className="p-4 rounded-2xl space-y-3"
              style={{
                background: 'linear-gradient(145deg, #1c1c38, #12122a)',
                border: '1px solid rgba(255,255,255,0.05)',
              }}
            >
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <BarChart3 size={14} className="text-amber-400" />
                Rarity Breakdown
              </h3>
              <div className="space-y-2">
                {rarityDistribution.slice(0, 8).map(([rarity, count], i) => {
                  const color = getRarityColor(rarity);
                  const pct = (count / maxRarityCount) * 100;
                  return (
                    <div key={rarity} className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-400 w-28 truncate shrink-0">{rarity}</span>
                      <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
                        <motion.div
                          className="h-full rounded-full"
                          style={{ background: color }}
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 0.6, delay: i * 0.05 }}
                        />
                      </div>
                      <span className="text-[11px] text-gray-500 font-bold w-8 text-right tabular-nums">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Type Breakdown */}
          {typeDistribution.length > 0 && (
            <div
              className="p-4 rounded-2xl space-y-3"
              style={{
                background: 'linear-gradient(145deg, #1c1c38, #12122a)',
                border: '1px solid rgba(255,255,255,0.05)',
              }}
            >
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <BarChart3 size={14} className="text-amber-400" />
                Type Breakdown
              </h3>
              <div className="space-y-2">
                {typeDistribution.map(([type, count], i) => {
                  const tc = TYPE_COLORS[type] ?? { color: '#9ca3af', bg: 'rgba(156,163,175,0.15)' };
                  const pct = (count / maxTypeCount) * 100;
                  return (
                    <div key={type} className="flex items-center gap-2">
                      <span className="text-[11px] font-medium w-20 shrink-0" style={{ color: tc.color }}>{type}</span>
                      <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
                        <motion.div
                          className="h-full rounded-full"
                          style={{ background: tc.color }}
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 0.6, delay: i * 0.05 }}
                        />
                      </div>
                      <span className="text-[11px] text-gray-500 font-bold w-8 text-right tabular-nums">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* Set Progress */}
      <motion.div variants={itemVariants}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <BarChart3 size={18} className="text-amber-400" />
            Set Progress
          </h2>
          <Link to="/sets" className="text-xs text-gray-500 hover:text-amber-400 transition-colors flex items-center gap-1">
            View all <ChevronRight size={14} />
          </Link>
        </div>

        {isLoading ? (
          <LoadingSkeleton count={3} type="set" />
        ) : setProgress.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-12 rounded-xl bg-white/2 border border-white/5"
          >
            <motion.div
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 2, repeat: Infinity }}
              className="text-4xl mb-3"
            >
              🎴
            </motion.div>
            <p className="text-gray-400 text-sm">No sets started yet</p>
            <Link to="/sets">
              <button className="mt-3 sort-pill sort-pill-amber text-xs font-medium">
                Start collecting
              </button>
            </Link>
          </motion.div>
        ) : (
          <div className="space-y-3">
            {setProgress.map(({ set, owned: ownedCount, progress }, i) => (
              <motion.div
                key={set.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                whileHover={{ x: 4 }}
              >
                <Link to={`/sets/${set.id}`}>
                  <div
                    className="p-4 rounded-2xl flex items-center gap-4 cursor-pointer transition-all hover:bg-white/4"
                    style={{
                      background: 'linear-gradient(145deg, #1c1c38, #12122a)',
                      border: progress === 100 ? '1px solid rgba(255,203,5,0.25)' : '1px solid rgba(255,255,255,0.05)',
                    }}
                  >
                    <div className="shrink-0 w-20 h-10 flex items-center justify-center">
                      {set.images.logo ? (
                        <img
                          src={set.images.logo}
                          alt={set.name}
                          loading="lazy"
                          decoding="async"
                          className="w-full h-full object-contain"
                          onError={(e) => {
                            const img = e.target as HTMLImageElement;
                            if (set.images.symbol) {
                              img.src = set.images.symbol;
                              img.className = 'w-8 h-8 object-contain';
                            } else {
                              img.style.display = 'none';
                            }
                          }}
                        />
                      ) : set.images.symbol ? (
                        <img src={set.images.symbol} alt={set.name} className="w-8 h-8 object-contain" />
                      ) : null}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1.5">
                        <p className="text-sm font-bold text-white truncate">{set.name}</p>
                        <span className="text-xs text-gray-500 shrink-0 ml-2 font-bold">
                          {ownedCount}/{set.total}
                        </span>
                      </div>
                      <div className="hp-bar-track">
                        <motion.div
                          className={`hp-bar-fill ${
                            progress === 100 ? 'hp-bar-full'
                            : progress >= 75  ? 'hp-bar-high'
                            : progress >= 40  ? 'hp-bar-mid'
                            : progress > 0    ? 'hp-bar-low'
                            : 'hp-bar-empty'
                          }`}
                          initial={{ width: 0 }}
                          animate={{ width: `${progress}%` }}
                          transition={{ duration: 1, delay: 0.2 + i * 0.1 }}
                        />
                      </div>
                    </div>
                    <div className="shrink-0 text-xs font-black" style={{ color: progress === 100 ? '#F59E0B' : '#6b7280' }}>
                      {progress}%
                    </div>
                    {progress === 100 && <span className="text-yellow-400 text-sm animate-pulse">✨</span>}
                    <ChevronRight size={14} className="text-gray-600" />
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Tips for new users */}
      {uniqueCards === 0 && (
        <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[            { icon: '🔍', title: 'Browse Sets', desc: 'Explore all Pokemon TCG sets ever released', link: '/sets', color: '#3b82f6' },
            { icon: '📦', title: 'Track Collection', desc: 'Mark cards as owned and track prices paid', link: '/collection', color: '#10b981' },
            { icon: '💫', title: 'Wishlist', desc: 'Save cards you want with target prices', link: '/wishlist', color: '#ec4899' },
          ].map((tip, i) => (
            <Link key={i} to={tip.link}>
              <motion.div
                whileHover={{ y: -5, scale: 1.03 }}
                className="p-5 rounded-2xl cursor-pointer h-full relative overflow-hidden"
                style={{
                  background: 'linear-gradient(145deg, #1c1c38, #12122a)',
                  border: `1px solid ${tip.color}28`,
                  boxShadow: `0 4px 20px ${tip.color}10`,
                }}
              >
                <div
                  className="absolute top-0 right-0 w-20 h-20 rounded-full pointer-events-none"
                  style={{
                    background: `radial-gradient(circle, ${tip.color}18, transparent 70%)`,
                    transform: 'translate(30%, -30%)',
                  }}
                />
                <span className="text-2xl">{tip.icon}</span>
                <h3 className="text-sm font-black text-white mt-2">{tip.title}</h3>
                <p className="text-xs text-gray-500 mt-1 font-semibold">{tip.desc}</p>
              </motion.div>
            </Link>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
