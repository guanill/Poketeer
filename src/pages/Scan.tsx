import { motion } from 'framer-motion';
import { ScanLine } from 'lucide-react';
import { CardScanner } from '../components/CardScanner';

export function Scan() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-2"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-400/10 border border-amber-400/20 flex items-center justify-center">
            <ScanLine size={20} className="text-amber-400" />
          </div>
          <h1 className="text-2xl font-black text-white">Card Scanner</h1>
        </div>
        <p className="text-gray-400 text-sm max-w-md">
          Take a photo or upload an image of a Pokémon card to identify it automatically
          using machine learning.
        </p>
      </motion.div>

      {/* How it works */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-3 gap-3"
      >
        {[
          { step: '1', label: 'Upload or snap',   desc: 'One or multiple cards at once' },
          { step: '2', label: 'Auto-identified',  desc: 'ResNet50 + OCR matching' },
          { step: '3', label: 'Add to collection', desc: 'From the scan queue' },
        ].map(({ step, label, desc }) => (
          <div key={step} className="p-3 rounded-xl bg-white/3 border border-white/8 text-center">
            <div className="w-7 h-7 rounded-full bg-amber-400/15 text-amber-400 text-xs font-black flex items-center justify-center mx-auto mb-2">
              {step}
            </div>
            <p className="text-white text-xs font-semibold">{label}</p>
            <p className="text-gray-500 text-xs mt-0.5">{desc}</p>
          </div>
        ))}
      </motion.div>

      {/* Scanner */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <CardScanner />
      </motion.div>
    </div>
  );
}
