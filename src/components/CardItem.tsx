import { useState, useRef } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { Plus, Minus, Heart, DollarSign, Eye } from 'lucide-react';
import type { PokemonCard } from '../types';
import { useCollectionStore } from '../store/collectionStore';
import { getCardMarketPrice, getRarityColor } from '../services/pokemonTCG';

interface CardItemProps {
  card: PokemonCard;
  onViewDetails?: (card: PokemonCard) => void;
}

export function CardItem({ card, onViewDetails }: CardItemProps) {
  const hasImage = !!card.images.small;
  const [imageLoaded, setImageLoaded] = useState(!hasImage);
  const cardRef = useRef<HTMLDivElement>(null);

  const owned = useCollectionStore(s => s.owned[card.id]);
  const inWishlist = useCollectionStore(s => s.isInWishlist(card.id));
  const addCard = useCollectionStore(s => s.addCard);
  const removeCard = useCollectionStore(s => s.removeCard);
  const addToWishlist = useCollectionStore(s => s.addToWishlist);
  const removeFromWishlist = useCollectionStore(s => s.removeFromWishlist);

  // 3D tilt effect
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [8, -8]), { stiffness: 300, damping: 30 });
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-8, 8]), { stiffness: 300, damping: 30 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width - 0.5;
    const ny = (e.clientY - rect.top) / rect.height - 0.5;
    x.set(nx);
    y.set(ny);
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  const marketPrice = getCardMarketPrice(card);
  const rarityColor = getRarityColor(card.rarity);
  const isOwned = !!owned;

  return (
    <motion.div
      ref={cardRef}
      style={{
        rotateX,
        rotateY,
        perspective: 1000,
        transformStyle: 'preserve-3d',
        background: 'linear-gradient(150deg, #1e1e3c 0%, #14142e 100%)',
        boxShadow: isOwned
          ? `0 10px 36px rgba(255,203,5,0.22), 0 0 0 2px rgba(255,203,5,0.45), inset 0 1px 0 rgba(255,255,255,0.07)`
          : '0 4px 18px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      initial={{ opacity: 0, scale: 0.9, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.9 }}
      whileHover={{ scale: 1.05, zIndex: 10 }}
      transition={{ type: 'spring', stiffness: 260, damping: 20 }}
      className={`relative rounded-2xl overflow-hidden cursor-pointer group ${
        isOwned
          ? 'ring-2 ring-yellow-400/55'
          : 'ring-1 ring-white/6'
      }`}
    >
      {/* Holographic overlay */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-10">
        <div
          className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
          style={{
            background: `linear-gradient(135deg, transparent 30%, ${rarityColor}15 50%, transparent 70%)`,
          }}
        />
      </div>

      {/* Rarity indicator */}
      <div
        className="absolute top-2 right-2 z-20 w-2.5 h-2.5 rounded-full"
        style={{ background: rarityColor, boxShadow: `0 0 8px ${rarityColor}, 0 0 16px ${rarityColor}60` }}
      />

      {/* Card Number */}
      <div className="absolute top-2 left-2 z-20 text-xs font-black text-gray-500 font-mono">
        #{card.number}
      </div>

      {/* Image */}
      <div className="pt-6 pb-2 px-3 flex justify-center" onClick={() => onViewDetails?.(card)}>
        <div className="relative w-full aspect-2.5/3.5 max-w-35">
          {!imageLoaded && (
            <div className="absolute inset-0 rounded-lg shimmer bg-gray-800" />
          )}
          {hasImage ? (
            <motion.img
              src={card.images.small}
              alt={card.name}
              className={`w-full h-full object-contain rounded-lg transition-opacity ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
              onLoad={() => setImageLoaded(true)}
              onError={() => setImageLoaded(true)}
              style={{ filter: isOwned ? 'none' : 'grayscale(30%) brightness(0.85)' }}
            />
          ) : (
            <div
              className="w-full h-full rounded-lg flex flex-col items-center justify-center gap-1"
              style={{
                background: 'linear-gradient(145deg, #1a1a3e, #0f0f2a)',
                border: '1px solid rgba(139,92,246,0.2)',
                filter: isOwned ? 'none' : 'grayscale(30%) brightness(0.85)',
              }}
            >
              <span className="text-2xl opacity-30">🃏</span>
              <span className="text-xs text-gray-600 text-center px-1 leading-tight">{card.name}</span>
            </div>
          )}
          {!isOwned && (
            <div className="absolute inset-0 rounded-lg bg-black/20 pointer-events-none" />
          )}
        </div>
      </div>

      {/* Card Info */}
      <div className="px-2 pb-2">
        <p className="text-xs font-bold text-white truncate text-center leading-tight">{card.name}</p>
        <div className="flex items-center justify-center gap-1 mt-0.5">
          <span className="text-xs" style={{ color: rarityColor }}>
            {card.rarity ?? 'Common'}
          </span>
        </div>
        {marketPrice && (
          <div className="flex items-center justify-center gap-1 mt-1">
            <DollarSign size={10} className="text-green-400" />
            <span className="text-xs text-green-400 font-mono">${marketPrice.toFixed(2)}</span>
          </div>
        )}
        {isOwned && (
          <div className="flex items-center justify-center mt-1">
            <span className="text-xs px-2 py-0.5 rounded-full font-black"
              style={{ background: 'rgba(245,158,11,0.16)', color: '#F59E0B', border: '1px solid rgba(245,158,11,0.28)' }}
            >
              ×{owned.quantity} owned
            </span>
          </div>
        )}
      </div>

      {/* Action Buttons — appear on hover */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        whileHover={{ opacity: 1, y: 0 }}
        className="absolute bottom-0 left-0 right-0 bg-linear-to-t from-[#0a0a1f] to-transparent p-2 flex items-center justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-20"
      >
        {isOwned ? (
          <motion.button
            whileTap={{ scale: 0.85 }}
            onClick={(e) => { e.stopPropagation(); removeCard(card.id); }}
            className="p-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/40 text-red-400 transition-colors"
            title="Remove from collection"
          >
            <Minus size={12} />
          </motion.button>
        ) : null}
        <motion.button
          whileTap={{ scale: 0.85 }}
          onClick={(e) => { e.stopPropagation(); addCard(card.id, marketPrice ?? undefined); }}
          className="p-1.5 rounded-lg bg-green-500/20 hover:bg-green-500/40 text-green-400 transition-colors"
          title="Add to collection"
        >
          <Plus size={12} />
        </motion.button>
        <motion.button
          whileTap={{ scale: 0.85 }}
          onClick={(e) => {
            e.stopPropagation();
            if (inWishlist) { removeFromWishlist(card.id); } else { addToWishlist(card.id, marketPrice ?? undefined); }
          }}
          className={`p-1.5 rounded-lg transition-colors ${
            inWishlist ? 'bg-pink-500/40 text-pink-400' : 'bg-pink-500/10 hover:bg-pink-500/30 text-pink-500'
          }`}
          title={inWishlist ? 'Remove from wishlist' : 'Add to wishlist'}
        >
          {inWishlist ? <Heart size={12} fill="currentColor" /> : <Heart size={12} />}
        </motion.button>
        <motion.button
          whileTap={{ scale: 0.85 }}
          onClick={(e) => { e.stopPropagation(); onViewDetails?.(card); }}
          className="p-1.5 rounded-lg bg-blue-500/20 hover:bg-blue-500/40 text-blue-400 transition-colors"
          title="View details"
        >
          <Eye size={12} />
        </motion.button>
      </motion.div>
    </motion.div>
  );
}
