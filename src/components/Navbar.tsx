import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LayoutDashboard, Layers, BookOpen, Heart, Search, ScanLine } from 'lucide-react';
import { useCollectionStore } from '../store/collectionStore';

function CardIcon({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 52"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Card body */}
      <rect x="2" y="2" width="36" height="48" rx="4" fill="#1a1040"
        stroke="url(#cardBorder)" strokeWidth="2" />
      {/* Inner frame */}
      <rect x="5" y="5" width="30" height="42" rx="2.5"
        fill="none" stroke="rgba(245,158,11,0.35)" strokeWidth="1" />
      {/* Top art area (gradient block) */}
      <rect x="7" y="8" width="26" height="18" rx="2"
        fill="url(#artGrad)" />
      {/* Art shine streak */}
      <path d="M9 10 L20 8 L21 26 L8 22 Z"
        fill="rgba(255,255,255,0.09)" />
      {/* Star burst — 4-point */}
      <path d="M20 13 L21.4 17 L25 18 L21.4 19 L20 23 L18.6 19 L15 18 L18.6 17 Z"
        fill="#F59E0B" opacity="0.95" />
      {/* Star inner shine */}
      <path d="M20 14.5 L20.9 17 L23 18 L20.9 19 L20 21.5 L19.1 19 L17 18 L19.1 17 Z"
        fill="rgba(255,255,255,0.3)" />
      {/* Name bar */}
      <rect x="7" y="28" width="18" height="3" rx="1.5"
        fill="rgba(245,158,11,0.5)" />
      {/* Sub line 1 */}
      <rect x="7" y="33" width="26" height="2" rx="1"
        fill="rgba(255,255,255,0.12)" />
      {/* Sub line 2 */}
      <rect x="7" y="37" width="20" height="2" rx="1"
        fill="rgba(255,255,255,0.08)" />
      {/* Bottom HP dots */}
      <circle cx="29" cy="43" r="2" fill="#8B5CF6" opacity="0.7" />
      <circle cx="24" cy="43" r="2" fill="#3b82f6" opacity="0.5" />
      {/* Corner sparkle */}
      <circle cx="32" cy="10" r="1.5" fill="rgba(255,255,255,0.6)" />
      <line x1="32" y1="7.5" x2="32" y2="12.5" stroke="rgba(255,255,255,0.4)" strokeWidth="0.8" />
      <line x1="29.5" y1="10" x2="34.5" y2="10" stroke="rgba(255,255,255,0.4)" strokeWidth="0.8" />
      <defs>
        <linearGradient id="cardBorder" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8B5CF6" />
          <stop offset="50%" stopColor="#F59E0B" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
        <linearGradient id="artGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2d1b69" />
          <stop offset="100%" stopColor="#1e3a5f" />
        </linearGradient>
      </defs>
    </svg>
  );
}

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sets', icon: Layers, label: 'All Sets' },
  { to: '/collection', icon: BookOpen, label: 'Collection' },
  { to: '/wishlist', icon: Heart, label: 'Wishlist' },
  { to: '/search', icon: Search, label: 'Search' },
  { to: '/scan', icon: ScanLine, label: 'Scan' },
];

export function Navbar() {
  const uniqueCards = useCollectionStore(s => s.getUniqueCards());
  const wishlistCount = useCollectionStore(s => s.wishlist.length);

  return (
    <>
    <nav className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md border-b top-nav-safe"
      style={{
        background: 'linear-gradient(180deg, rgba(8,5,18,0.97) 0%, rgba(10,5,20,0.95) 100%)',
        borderColor: 'rgba(139,92,246,0.2)',
        boxShadow: '0 1px 0 rgba(245,158,11,0.08), 0 4px 24px rgba(0,0,0,0.5)',
      }}
    >
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        {/* Logo */}
        <NavLink to="/" className="flex items-center gap-2.5 group">
          <motion.div
            whileHover={{ y: -2, scale: 1.12, rotateZ: -4 }}
            transition={{ duration: 0.3, type: 'spring' }}
            className="shrink-0"
            style={{ filter: 'drop-shadow(0 0 8px rgba(139,92,246,0.6))' }}
          >
            <CardIcon size={30} />
          </motion.div>
          <span className="text-xl font-black tracking-tight" style={{ fontFamily: "'Nunito', sans-serif" }}>
            <span className="text-gradient-gold">Poke</span>
            <span className="text-white">teer</span>
          </span>
        </NavLink>

        {/* Nav Links */}
        <div className="hidden md:flex items-center gap-0.5">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} end={to === '/'}>
              {({ isActive }) => (
                <motion.div
                  whileHover={{ scale: 1.05, y: -1 }}
                  whileTap={{ scale: 0.95 }}
                  className={`relative px-4 py-2 rounded-xl flex items-center gap-2 text-sm font-bold transition-all ${
                    isActive
                      ? 'text-yellow-300 bg-yellow-400/12'
                      : 'text-gray-400 hover:text-white hover:bg-white/6'
                  }`}
                  style={isActive ? { textShadow: '0 0 12px rgba(245,158,11,0.5)' } : undefined}
                >
                  <Icon size={15} />
                  {label}
                  {isActive && (
                    <motion.div
                      layoutId="nav-indicator"
                      className="absolute bottom-0 left-1/2 -translate-x-1/2 w-5 h-0.5 rounded-full"
                      style={{ background: 'linear-gradient(90deg, #8B5CF6, #F59E0B)' }}
                    />
                  )}
                </motion.div>
              )}
            </NavLink>
          ))}
        </div>

        {/* Desktop Stats Pills */}
        <div className="hidden md:flex items-center gap-2">
          <motion.div
            whileHover={{ scale: 1.05 }}
            className="px-3 py-1.5 rounded-full text-xs font-bold flex items-center gap-1.5"
            style={{
              background: 'rgba(139,92,246,0.12)',
              border: '1px solid rgba(139,92,246,0.25)',
              color: '#c4b5fd',
            }}
          >
            <CardIcon size={14} />
            {uniqueCards} cards
          </motion.div>
          {wishlistCount > 0 && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              whileHover={{ scale: 1.05 }}
              className="px-3 py-1.5 rounded-full text-xs font-bold"
              style={{
                background: 'rgba(244,63,94,0.15)',
                border: '1px solid rgba(244,63,94,0.3)',
                color: '#fb7185',
              }}
            >
              ♥ {wishlistCount}
            </motion.div>
          )}
        </div>
      </div>
    </nav>

    {/* ── Mobile Bottom Tab Bar (Android) ───────────────────────── */}
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50"
      style={{
        background: 'linear-gradient(180deg, rgba(10,6,22,0.98) 0%, rgba(7,5,15,0.99) 100%)',
        borderTop: '1px solid rgba(139,92,246,0.2)',
        boxShadow: '0 -4px 32px rgba(0,0,0,0.7)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
    >
      <div className="flex items-stretch h-14">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} end={to === '/'} className="flex-1">
            {({ isActive }) => (
              <motion.div
                whileTap={{ scale: 0.82 }}
                className="relative flex flex-col items-center justify-center h-full gap-0.5"
              >
                {/* Active top line */}
                {isActive && (
                  <motion.div
                    layoutId="bottom-tab-line"
                    className="absolute top-0 inset-x-2 h-0.5 rounded-full"
                    style={{ background: 'linear-gradient(90deg, #8B5CF6, #F59E0B)' }}
                  />
                )}
                <div style={isActive ? { filter: 'drop-shadow(0 0 6px rgba(139,92,246,0.8))' } : undefined}>
                  <Icon
                    size={22}
                    style={{ color: isActive ? '#a78bfa' : '#6b7280' }}
                    strokeWidth={isActive ? 2.2 : 1.8}
                  />
                </div>
                <span
                  className="text-[9px] font-bold tracking-wide"
                  style={{ color: isActive ? '#a78bfa' : '#6b7280' }}
                >
                  {label}
                </span>
              </motion.div>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  </>
  );
}
