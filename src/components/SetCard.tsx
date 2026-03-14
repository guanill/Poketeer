import { memo } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Calendar, Hash } from 'lucide-react';
import type { PokemonSet } from '../types';
import { useCollectionStore } from '../store/collectionStore';
import { ProgressRing } from './ProgressRing';

interface SetCardProps {
  set: PokemonSet;
  index?: number;
  ownedCardIds: string[];
}

export const SetCard = memo(function SetCard({ set, index = 0, ownedCardIds }: SetCardProps) {
  const navigate = useNavigate();
  const ownedCount = useCollectionStore(s => s.getOwnedCount(set.id, ownedCardIds));
  const progress = set.total > 0 ? Math.round((ownedCount / set.total) * 100) : 0;

  const getProgressColor = () => {
    if (progress === 100) return '#F59E0B';
    if (progress >= 75) return '#10b981';
    if (progress >= 50) return '#3b82f6';
    if (progress >= 25) return '#8b5cf6';
    return '#6b7280';
  };

  const isComplete = progress === 100;
  // Cap stagger so cards beyond the 20th don't wait 4+ seconds to animate in
  const delay = Math.min(index, 20) * 0.04;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: 'spring', stiffness: 240, damping: 22 }}
      whileHover={{ y: -5, scale: 1.025 }}
      onClick={() => navigate(`/sets/${set.id}${set.language && set.language !== 'en' ? `?lang=${set.language}` : ''}`)}
      className="relative rounded-2xl overflow-hidden cursor-pointer group"
      style={{
        background: 'linear-gradient(150deg, #1c1c38 0%, #12122a 100%)',
        boxShadow: isComplete
          ? '0 8px 32px rgba(255,203,5,0.22), 0 2px 8px rgba(0,0,0,0.5)'
          : '0 4px 18px rgba(0,0,0,0.4)',
        border: isComplete
          ? '1px solid rgba(255,203,5,0.35)'
          : '1px solid rgba(255,255,255,0.06)',
        transition: 'box-shadow 0.2s',
      }}
    >
      {isComplete && (
        <div className="absolute inset-0 pointer-events-none z-10">
          <div className="absolute inset-0 bg-linear-to-br from-yellow-400/5 to-transparent" />
          <motion.div
            animate={{ opacity: [0.3, 0.7, 0.3] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute top-2 right-2 text-yellow-400 text-lg"
          >
            ✨
          </motion.div>
        </div>
      )}

      {/* Progress color strip */}
      <div
        className="absolute top-0 left-0 right-0 h-0.75 z-10"
        style={{
          background: isComplete
            ? 'linear-gradient(90deg, #8B5CF6, #F59E0B, #3b82f6)'
            : `linear-gradient(90deg, ${getProgressColor()}, ${getProgressColor()}80)`,
          opacity: 0.9,
        }}
      />

      {/* Set logo / banner */}
      <div className="relative h-16 flex items-center justify-center overflow-hidden"
        style={{ background: set.images.logo ? undefined : `linear-gradient(135deg, ${getProgressColor()}18 0%, ${getProgressColor()}06 100%)` }}
      >
        {set.images.logo ? (
          <>
            <div className="absolute inset-0 bg-white/3" />
            <img
              src={set.images.logo}
              alt={set.name}
              loading={index < 6 ? 'eager' : 'lazy'}
              decoding="async"
              className="relative h-full w-full object-contain px-4 py-2"
              onError={(e) => {
                const img = e.target as HTMLImageElement;
                img.style.display = 'none';
                const banner = img.parentElement?.querySelector('.name-banner') as HTMLElement | null;
                if (banner) banner.style.display = 'flex';
              }}
            />
            {/* shown only if img 404s */}
            <div className="name-banner absolute inset-0 items-center justify-center px-3" style={{ display: 'none' }}>
              <span className="text-white font-bold text-sm text-center line-clamp-2 leading-tight drop-shadow">{set.name}</span>
            </div>
          </>
        ) : (
          /* No logo available (JP/TH) — styled name banner */
          <>
            {/* decorative blurred circle */}
            <div className="absolute -right-4 -top-4 w-20 h-20 rounded-full opacity-20 blur-xl"
              style={{ background: getProgressColor() }} />
            <div className="absolute -left-4 -bottom-4 w-16 h-16 rounded-full opacity-10 blur-xl"
              style={{ background: getProgressColor() }} />
            <div className="relative flex items-center gap-2.5 px-3 w-full">
              <div
                className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center text-xs font-black leading-none"
                style={{ background: getProgressColor() + '30', color: getProgressColor(), border: `1px solid ${getProgressColor()}50` }}
              >
                {Array.from(set.name)[0]}
              </div>
              <span className="text-white/85 font-bold text-sm line-clamp-2 leading-tight">{set.name}</span>
            </div>
          </>
        )}
      </div>

      <div className="p-3 pt-2.5">
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <h3 className="font-bold text-white text-sm line-clamp-1 group-hover:text-yellow-400 transition-colors">
              {set.name}
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">{set.series}</p>
            <div className="flex items-center gap-3 mt-1.5">
              <div className="flex items-center gap-1 text-xs text-gray-500">
                <Hash size={10} />
                {set.total} cards
              </div>
              <div className="flex items-center gap-1 text-xs text-gray-500">
                <Calendar size={10} />
                {set.releaseDate?.split('/')[0] ?? '—'}
              </div>
            </div>
          </div>

          {/* Progress Ring */}
          <ProgressRing
            progress={progress}
            size={44}
            strokeWidth={4}
            color={getProgressColor()}
          >
            <span className="text-xs font-bold" style={{ color: getProgressColor() }}>
              {progress}%
            </span>
          </ProgressRing>
        </div>

        {/* HP-bar style progress */}
        <div className="mt-2.5">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-gray-500 font-bold">
              {ownedCount}/{set.total} collected
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
              transition={{ duration: 0.8, delay: delay + 0.2, ease: [0.34, 1.56, 0.64, 1] }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
});
