import { motion } from 'framer-motion';
import { AlertCircle, RotateCw } from 'lucide-react';

interface QueryErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  compact?: boolean;
}

export function QueryErrorState({
  title = "Couldn't load this",
  message = 'Check your connection and try again.',
  onRetry,
  compact = false,
}: QueryErrorStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={`surface-deep rounded-2xl text-center ${compact ? 'py-10 px-4' : 'py-20 px-6'}`}
      style={{ border: '1px solid rgba(239,68,68,0.18)' }}
      role="alert"
    >
      <div className="inline-flex items-center justify-center w-10 h-10 rounded-full mb-3"
        style={{ background: 'rgba(239,68,68,0.14)', border: '1px solid rgba(239,68,68,0.3)' }}
      >
        <AlertCircle size={18} className="text-red-400" />
      </div>
      <p className="text-sm font-bold text-gray-200">{title}</p>
      <p className="text-xs text-gray-500 mt-1">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-red-500/15 hover:bg-red-500/25 text-red-300 border border-red-500/25 transition-colors"
        >
          <RotateCw size={12} />
          Retry
        </button>
      )}
    </motion.div>
  );
}
