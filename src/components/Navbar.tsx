import { useState, useRef, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Layers, BookOpen, Heart, Search, ScanLine, LogIn, LogOut, User } from 'lucide-react';
import { useCollectionStore } from '../store/collectionStore';
import { useAuth } from '../lib/auth';

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

function UserMenu() {
  const { user, signInWithGoogle, signInWithEmail, signUp, signOut, loading } = useAuth();
  const [open, setOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'pick' | 'email'>('pick');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
        setAuthMode('pick');
        setError('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      if (isSignUp) {
        await signUp(email, password);
        setError('Check your email for a confirmation link!');
      } else {
        await signInWithEmail(email, password);
        setOpen(false);
        setAuthMode('pick');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return null;

  if (!user) {
    return (
      <div ref={menuRef} className="relative">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-colors"
          style={{
            background: 'rgba(245,158,11,0.12)',
            border: '1px solid rgba(245,158,11,0.25)',
            color: '#fcd34d',
          }}
        >
          <LogIn size={13} />
          <span className="hidden sm:inline">Sign in</span>
        </motion.button>
        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: -4 }}
              transition={{ duration: 0.15 }}
              className="absolute right-0 mt-2 w-64 rounded-xl overflow-hidden z-50"
              style={{
                background: 'linear-gradient(145deg, #1a1a2e, #13132a)',
                border: '1px solid rgba(139,92,246,0.2)',
                boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
              }}
            >
              {authMode === 'pick' ? (
                <div className="p-3 space-y-2">
                  <p className="text-xs font-bold text-white text-center mb-3">Sign in to sync your collection</p>
                  <button
                    onClick={() => { signInWithGoogle(); setOpen(false); }}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold bg-white text-gray-800 hover:bg-gray-200 hover:scale-[1.02] active:scale-[0.98] transition-all"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                    Continue with Google
                  </button>
                  <div className="flex items-center gap-2 my-1">
                    <div className="flex-1 h-px bg-white/10" />
                    <span className="text-[10px] text-gray-600">or</span>
                    <div className="flex-1 h-px bg-white/10" />
                  </div>
                  <button
                    onClick={() => setAuthMode('email')}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10 transition-colors"
                  >
                    <User size={13} />
                    Continue with Email
                  </button>
                </div>
              ) : (
                <form onSubmit={handleEmailSubmit} className="p-3 space-y-2">
                  <button
                    type="button"
                    onClick={() => { setAuthMode('pick'); setError(''); }}
                    className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    &larr; Back
                  </button>
                  <p className="text-xs font-bold text-white">{isSignUp ? 'Create account' : 'Sign in with email'}</p>
                  <input
                    type="email"
                    placeholder="Email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-600 outline-none focus:border-violet-500/50"
                  />
                  <input
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    minLength={6}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-600 outline-none focus:border-violet-500/50"
                  />
                  {error && (
                    <p className={`text-[10px] ${error.includes('Check your email') ? 'text-emerald-400' : 'text-red-400'}`}>{error}</p>
                  )}
                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full py-2 rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
                    style={{
                      background: 'linear-gradient(135deg, #F59E0B, #d97706)',
                      color: '#000',
                    }}
                  >
                    {submitting ? '...' : isSignUp ? 'Create Account' : 'Sign In'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setIsSignUp(!isSignUp); setError(''); }}
                    className="w-full text-[10px] text-gray-500 hover:text-gray-300 transition-colors py-1"
                  >
                    {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
                  </button>
                </form>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  const avatar = user.user_metadata?.avatar_url;
  const name = user.user_metadata?.full_name || user.email?.split('@')[0] || 'User';

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full overflow-hidden border-2 border-violet-500/40 hover:border-violet-500/70 transition-colors"
      >
        {avatar ? (
          <img src={avatar} alt={name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full bg-violet-500/20 flex items-center justify-center">
            <User size={14} className="text-violet-400" />
          </div>
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-48 rounded-xl overflow-hidden z-50"
            style={{
              background: 'linear-gradient(145deg, #1a1a2e, #13132a)',
              border: '1px solid rgba(139,92,246,0.2)',
              boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
            }}
          >
            <div className="px-3 py-2.5 border-b border-white/5">
              <p className="text-xs font-bold text-white truncate">{name}</p>
              <p className="text-[10px] text-gray-500 truncate">{user.email}</p>
            </div>
            <button
              onClick={() => { signOut(); setOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-2.5 text-xs text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <LogOut size={13} />
              Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

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

        {/* Right side: stats + auth */}
        <div className="flex items-center gap-2">
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
          <UserMenu />
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
