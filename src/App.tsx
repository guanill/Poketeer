import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HashRouter, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Navbar } from './components/Navbar';
import { Dashboard } from './pages/Dashboard';
import { Sets } from './pages/Sets';
import { SetDetail } from './pages/SetDetail';
import { Collection } from './pages/Collection';
import { Wishlist } from './pages/Wishlist';
import { Search } from './pages/Search';
import { Scan } from './pages/Scan';
import { AuthProvider } from './lib/auth';
import { AuthSync } from './components/AuthSync';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

function AppRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <motion.main
        key={location.pathname}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -12 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
        className="main-content px-4 max-w-7xl mx-auto"
      >
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sets" element={<Sets />} />
          <Route path="/sets/:setId" element={<SetDetail />} />
          <Route path="/collection" element={<Collection />} />
          <Route path="/wishlist" element={<Wishlist />} />
          <Route path="/search" element={<Search />} />
          <Route path="/scan" element={<Scan />} />
        </Routes>
      </motion.main>
    </AnimatePresence>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <HashRouter>
          <div className="min-h-screen" style={{ background: '#07070f' }}>
            {/* Ambient background rings */}
            <div aria-hidden="true" style={{
              position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden',
            }}>
              <div style={{
                position: 'absolute', width: 500, height: 500, borderRadius: '50%',
                border: '50px solid rgba(139,92,246,0.03)',
                right: -160, top: -160,
              }} />
              <div style={{
                position: 'absolute', width: 320, height: 320, borderRadius: '50%',
                border: '30px solid rgba(139,92,246,0.02)',
                right: -60, top: -60,
              }} />
              <div style={{
                position: 'absolute', width: 420, height: 420, borderRadius: '50%',
                border: '40px solid rgba(59,130,246,0.03)',
                left: -140, bottom: -140,
              }} />
            </div>
            <AuthSync />
            <Navbar />
            <AppRoutes />
          </div>
        </HashRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;

