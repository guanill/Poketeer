import { motion } from 'framer-motion';
import { ScanLine } from 'lucide-react';
import { CardScanner } from '../components/CardScanner';

export function Scan() {
  return (
    <div className="space-y-5 max-sm:overflow-hidden max-sm:h-[calc(100svh-10rem)]">
      {/* Header — desktop only, mobile has bottom tab label */}
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        className="hidden sm:block space-y-1"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-400/10 border border-amber-400/20 flex items-center justify-center">
            <ScanLine size={20} className="text-amber-400" />
          </div>
          <h1 className="text-2xl font-black text-white">Card Scanner</h1>
        </div>
        <p className="text-gray-500 text-sm">
          Snap a photo or upload an image to identify cards instantly
        </p>
      </motion.div>

      {/* Scanner */}
      <CardScanner />
    </div>
  );
}
