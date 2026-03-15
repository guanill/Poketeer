import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Plus, Minus, Heart, DollarSign, Package, Star, ExternalLink } from 'lucide-react';
import type { PokemonCard, CardCondition, CardVariant } from '../types';
import { useCollectionStore } from '../store/collectionStore';
import { getCardMarketPrice, getRarityColor, getAvailableVariants } from '../services/pokemonTCG';

const VARIANT_META: Record<CardVariant, { label: string; color: string; bg: string }> = {
  normal: { label: 'Normal', color: '#9ca3af', bg: 'rgba(156,163,175,0.15)' },
  holofoil: { label: 'Holofoil', color: '#fbbf24', bg: 'rgba(251,191,36,0.15)' },
  reverseHolofoil: { label: 'Reverse Holo', color: '#a78bfa', bg: 'rgba(167,139,250,0.15)' },
  firstEdition: { label: '1st Edition', color: '#f472b6', bg: 'rgba(244,114,182,0.15)' },
};

interface CardDetailModalProps {
  card: PokemonCard | null;
  onClose: () => void;
  marketPrice?: number | null;
}

const CONDITIONS: CardCondition[] = ['Mint', 'Near Mint', 'Excellent', 'Good', 'Light Play', 'Played', 'Poor'];

export function CardDetailModal({ card, onClose, marketPrice: marketPriceProp }: CardDetailModalProps) {
  const [pricePaid, setPricePaid] = useState('');
  const [condition, setCondition] = useState<CardCondition>('Near Mint');
  const [notes, setNotes] = useState('');
  const [manualPriceInput, setManualPriceInput] = useState('');

  const owned = useCollectionStore(s => card ? s.owned[card.id] : undefined);
  const inWishlist = useCollectionStore(s => card ? s.isInWishlist(card.id) : false);
  const customPrices = useCollectionStore(s => s.customPrices);
  const addCard = useCollectionStore(s => s.addCard);
  const removeCard = useCollectionStore(s => s.removeCard);
  const updateCard = useCollectionStore(s => s.updateCard);
  const toggleVariant = useCollectionStore(s => s.toggleVariant);
  const addToWishlist = useCollectionStore(s => s.addToWishlist);
  const removeFromWishlist = useCollectionStore(s => s.removeFromWishlist);
  const setCustomPriceStore = useCollectionStore(s => s.setCustomPrice);

  if (!card) return null;

  // Use passed-in price first, then embedded tcgplayer data, then stored custom price
  const marketPrice = marketPriceProp ?? getCardMarketPrice(card) ?? customPrices[card.id] ?? null;

  const handleSaveManualPrice = () => {
    const val = parseFloat(manualPriceInput);
    if (!isNaN(val) && val > 0) {
      setCustomPriceStore(card.id, val);
      setManualPriceInput('');
    }
  };
  const rarityColor = getRarityColor(card.rarity);
  const isOwned = !!owned;

  const prices = card.tcgplayer?.prices;
  const priceVariants = prices
    ? Object.entries(prices).map(([variant, p]) => ({
        variant,
        market: p?.market,
        low: p?.low,
        high: p?.high,
      }))
    : [];

  const handleAddToCollection = () => {
    addCard(card.id, pricePaid ? parseFloat(pricePaid) : marketPrice ?? undefined, condition, notes || undefined);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)' }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.85, y: 40 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.85, y: 40 }}
          transition={{ type: 'spring', stiffness: 300, damping: 25 }}
          className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl"
          style={{
            background: 'linear-gradient(145deg, #1a1a2e, #0f0f2a)',
            border: `1px solid ${rarityColor}40`,
            boxShadow: `0 25px 80px rgba(0,0,0,0.8), 0 0 40px ${rarityColor}20`,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={onClose}
            className="absolute top-3 right-3 z-10 p-2 rounded-xl bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
          >
            <X size={16} />
          </button>

          <div className="p-5">
            {/* Top section — stacks on mobile, side-by-side on desktop */}
            <div className="flex flex-col sm:flex-row gap-5">
              {/* Card Image */}
              <div className="shrink-0 flex justify-center sm:block">
                <motion.div
                  whileHover={{ scale: 1.05, rotateY: 5 }}
                  transition={{ type: 'spring', stiffness: 200 }}
                  className="relative"
                >
                  {(card.images.large || card.images.small) ? (
                    <img
                      src={card.images.large || card.images.small}
                      alt={card.name}
                      className="w-36 sm:w-40 rounded-xl shadow-2xl"
                      style={{ boxShadow: `0 20px 40px ${rarityColor}40` }}
                    />
                  ) : (
                    <div
                      className="w-36 sm:w-40 rounded-xl flex flex-col items-center justify-center gap-2"
                      style={{
                        height: '220px',
                        background: 'linear-gradient(145deg, #1a1a3e, #0f0f2a)',
                        border: `1px solid ${rarityColor}40`,
                        boxShadow: `0 20px 40px ${rarityColor}20`,
                      }}
                    >
                      <span className="text-4xl opacity-30">🃏</span>
                      <span className="text-xs text-gray-500 text-center px-2">{card.name}</span>
                    </div>
                  )}
                  {isOwned && (
                    <motion.div
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      className="absolute -top-2 -right-2 w-7 h-7 rounded-full bg-yellow-400 flex items-center justify-center shadow-lg"
                    >
                      <Star size={14} className="text-black" fill="currentColor" />
                    </motion.div>
                  )}
                </motion.div>
              </div>

              {/* Card Info */}
              <div className="flex-1 min-w-0">
                <div>
                  <h2 className="text-xl font-black text-white leading-tight">{card.name}</h2>
                  <div className="flex items-center gap-2 mt-1 flex-wrap">
                    <span className="text-sm font-semibold" style={{ color: rarityColor }}>{card.rarity ?? 'Common'}</span>
                    <span className="text-xs text-gray-600">·</span>
                    <span className="text-xs text-gray-500">{card.set.name} #{card.number}</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5 mt-3">
                  {card.types?.map(type => (
                    <span
                      key={type}
                      className="px-2.5 py-1 rounded-full text-xs font-semibold bg-white/10 text-white capitalize"
                    >
                      {type}
                    </span>
                  ))}
                  {card.hp && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-red-500/20 text-red-400">
                      {card.hp} HP
                    </span>
                  )}
                  {card.supertype && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/20 text-blue-400">
                      {card.supertype}
                    </span>
                  )}
                </div>

                {card.artist && (
                  <p className="text-xs text-gray-500 mt-2">Artist: <span className="text-gray-300">{card.artist}</span></p>
                )}

                {/* Market Price */}
                <div className="mt-3 p-3 rounded-xl border border-white/8" style={{ background: 'linear-gradient(135deg, rgba(16,185,129,0.06), rgba(16,185,129,0.02))' }}>
                  {marketPrice ? (
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Market Price</p>
                        <p className="text-2xl font-black text-green-400 mt-0.5">${marketPrice.toFixed(2)}</p>
                      </div>
                      <div className="w-9 h-9 rounded-xl bg-green-500/15 flex items-center justify-center">
                        <DollarSign size={18} className="text-green-400" />
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Market Price</p>
                      <p className="text-xs text-gray-600 italic">No price data available</p>
                      <div className="flex gap-2 min-w-0">
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="Set price manually..."
                          value={manualPriceInput}
                          onChange={e => setManualPriceInput(e.target.value)}
                          className="flex-1 min-w-0 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-green-400/50"
                        />
                        <button
                          onClick={handleSaveManualPrice}
                          disabled={!manualPriceInput || isNaN(parseFloat(manualPriceInput))}
                          className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold bg-green-500/20 text-green-400 hover:bg-green-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  )}
                  {priceVariants.length > 0 && (
                    <div className="mt-2.5 space-y-1">
                      {priceVariants.map(({ variant, market, low, high }) => (
                        <div key={variant} className="flex items-center justify-between rounded-lg px-2.5 py-1.5 bg-black/20">
                          <span className="text-[11px] text-gray-400 capitalize font-medium">{variant.replace(/([A-Z])/g, ' $1')}</span>
                          <div className="flex items-center gap-2.5 text-[11px]">
                            {low != null && <span className="text-gray-600">${low.toFixed(2)}</span>}
                            {market != null && <span className="text-green-400 font-bold">${market.toFixed(2)}</span>}
                            {high != null && <span className="text-gray-600">${high.toFixed(2)}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Collection Actions */}
            <div className="mt-5 pt-4 border-t border-white/5">
              {isOwned ? (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-3"
                >
                  <div className="p-3 rounded-xl bg-yellow-400/10 border border-yellow-400/20 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-semibold text-yellow-400">In Your Collection</p>
                        <p className="text-xs text-gray-400 mt-0.5">
                          {owned.quantity}× · {owned.condition} ·
                          {owned.pricePaid ? ` Paid: $${owned.pricePaid.toFixed(2)}` : ' Price not set'}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => updateCard(card.id, { quantity: owned.quantity + 1 })}
                          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-white transition-colors"
                        >
                          <Plus size={14} />
                        </button>
                        <button
                          onClick={() => owned.quantity > 1
                            ? updateCard(card.id, { quantity: owned.quantity - 1 })
                            : removeCard(card.id)
                          }
                          className="p-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors"
                        >
                          <Minus size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Variant toggles — only show variants this card actually comes in */}
                    {(() => {
                      const available = getAvailableVariants(card);
                      return available.length > 1 || (available.length === 1 && available[0] !== 'normal') ? (
                        <div>
                          <p className="text-xs text-gray-500 mb-1.5">Variants owned</p>
                          <div className="flex flex-wrap gap-1.5">
                            {available.map(key => {
                              const { label, color, bg } = VARIANT_META[key];
                              const active = owned.variants?.includes(key);
                              return (
                                <button
                                  key={key}
                                  onClick={() => toggleVariant(card.id, key)}
                                  className="px-2.5 py-1 rounded-lg text-xs font-bold transition-all"
                                  style={{
                                    background: active ? bg : 'rgba(255,255,255,0.04)',
                                    color: active ? color : '#6b7280',
                                    border: `1px solid ${active ? color + '50' : 'rgba(255,255,255,0.08)'}`,
                                    boxShadow: active ? `0 0 8px ${color}30` : 'none',
                                  }}
                                >
                                  {label}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ) : null;
                    })()}
                  </div>
                </motion.div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-white">Add to Collection</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">Price Paid ($)</label>
                      <input
                        type="number"
                        placeholder={marketPrice ? `Market: $${marketPrice.toFixed(2)}` : '0.00'}
                        value={pricePaid}
                        onChange={(e) => setPricePaid(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-yellow-400/50"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">Condition</label>
                      <select
                        value={condition}
                        onChange={(e) => setCondition(e.target.value as CardCondition)}
                        className="w-full bg-[#1a1a2e] border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400/50"
                      >
                        {CONDITIONS.map(c => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  </div>
                  <input
                    type="text"
                    placeholder="Notes (optional)"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-yellow-400/50"
                  />
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={handleAddToCollection}
                    className="w-full py-2.5 rounded-xl font-bold text-sm text-black transition-all"
                    style={{ background: 'linear-gradient(135deg, #F59E0B, #d97706)' }}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <Package size={16} />
                      Add to Collection
                    </div>
                  </motion.button>
                </div>
              )}

              {/* Wishlist */}
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => inWishlist ? removeFromWishlist(card.id) : addToWishlist(card.id, marketPrice ?? undefined)}
                className={`mt-2 w-full py-2.5 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 ${
                  inWishlist
                    ? 'bg-pink-500/30 text-pink-400 border border-pink-500/30'
                    : 'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-pink-400 border border-white/10'
                }`}
              >
                <Heart size={16} fill={inWishlist ? 'currentColor' : 'none'} />
                {inWishlist ? 'Remove from Wishlist' : 'Add to Wishlist'}
              </motion.button>

              {card.tcgplayer?.url && (
                <a
                  href={card.tcgplayer.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 w-full py-2 rounded-xl text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center justify-center gap-1"
                >
                  <ExternalLink size={12} />
                  View on TCGPlayer
                </a>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
