import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { useConfirmStore } from '../store/confirmStore';

export function ConfirmDialog() {
  const isOpen       = useConfirmStore(s => s.isOpen);
  const title        = useConfirmStore(s => s.title);
  const message      = useConfirmStore(s => s.message);
  const confirmText  = useConfirmStore(s => s.confirmText);
  const cancelText   = useConfirmStore(s => s.cancelText);
  const tone         = useConfirmStore(s => s.tone);
  const handleConfirm = useConfirmStore(s => s.handleConfirm);
  const handleCancel  = useConfirmStore(s => s.handleCancel);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleCancel();
      if (e.key === 'Enter') handleConfirm();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, handleCancel, handleConfirm]);

  const isDanger = tone === 'danger';

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="confirm-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={handleCancel}
          className="fixed inset-0 z-[110] flex items-center justify-center p-4"
          style={{ background: 'rgba(3,2,8,0.72)', backdropFilter: 'blur(4px)' }}
        >
          <motion.div
            key="confirm-panel"
            initial={{ opacity: 0, scale: 0.94, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            onClick={e => e.stopPropagation()}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby="confirm-message"
            className="surface-panel w-full max-w-sm rounded-2xl overflow-hidden"
            style={{
              border: `1px solid ${isDanger ? 'rgba(239,68,68,0.3)' : 'rgba(139,92,246,0.25)'}`,
              boxShadow: '0 20px 60px rgba(0,0,0,0.7)',
            }}
          >
            <div className="p-5">
              <div className="flex items-start gap-3 mb-3">
                <div
                  className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center"
                  style={{
                    background: isDanger ? 'rgba(239,68,68,0.15)' : 'rgba(139,92,246,0.15)',
                    border: `1px solid ${isDanger ? 'rgba(239,68,68,0.35)' : 'rgba(139,92,246,0.35)'}`,
                  }}
                >
                  <AlertTriangle
                    size={16}
                    style={{ color: isDanger ? '#f87171' : '#c4b5fd' }}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <h2 id="confirm-title" className="text-base font-black text-white leading-tight">
                    {title}
                  </h2>
                  <p id="confirm-message" className="mt-1.5 text-xs text-gray-400 leading-relaxed">
                    {message}
                  </p>
                </div>
              </div>
              <div className="flex gap-2 mt-5">
                <button
                  onClick={handleCancel}
                  className="flex-1 py-2.5 rounded-lg text-xs font-bold bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10 transition-colors"
                >
                  {cancelText}
                </button>
                <button
                  onClick={handleConfirm}
                  autoFocus
                  className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-colors ${isDanger ? 'btn-gradient-danger' : 'btn-gradient-amber'}`}
                  style={
                    isDanger
                      ? { color: '#fff', boxShadow: '0 4px 16px rgba(239,68,68,0.35)' }
                      : { color: '#1a0a00', boxShadow: '0 4px 16px rgba(245,158,11,0.35)' }
                  }
                >
                  {confirmText}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
