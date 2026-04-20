import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ScanLine } from 'lucide-react';
import { useScanStore } from '../store/scanStore';
import { CardScanner } from './CardScanner';

export function ScanModal() {
  const isOpen = useScanStore(s => s.isOpen);
  const closeScanner = useScanStore(s => s.closeScanner);

  useEffect(() => {
    if (!isOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeScanner();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [isOpen, closeScanner]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="scan-modal"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[100] flex flex-col"
          style={{
            background: 'linear-gradient(180deg, #07070f 0%, #0a0618 100%)',
            paddingTop: 'env(safe-area-inset-top)',
            paddingBottom: 'env(safe-area-inset-bottom)',
          }}
        >
          {/* Top bar */}
          <div className="shrink-0 flex items-center justify-between px-4 h-14 border-b"
            style={{ borderColor: 'rgba(139,92,246,0.2)' }}
          >
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-amber-400/10 border border-amber-400/20 flex items-center justify-center">
                <ScanLine size={16} className="text-amber-400" />
              </div>
              <span className="text-sm font-black text-white">Card Scanner</span>
            </div>
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={closeScanner}
              className="w-9 h-9 rounded-full flex items-center justify-center bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
              aria-label="Close scanner"
            >
              <X size={18} />
            </motion.button>
          </div>

          {/* Scanner */}
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.25, delay: 0.05 }}
            className="flex-1 min-h-0 overflow-y-auto px-4 py-3"
          >
            <CardScanner />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
