import { motion } from 'framer-motion';
import { Settings as SettingsIcon, Globe } from 'lucide-react';
import { useSettingsStore } from '../store/settingsStore';

type Lang = 'en' | 'ja' | 'th';

const LANGUAGES: { id: Lang; flag: string; label: string; desc: string }[] = [
  { id: 'en', flag: '\uD83C\uDDEC\uD83C\uDDE7', label: 'English', desc: 'Scarlet & Violet, Sword & Shield, Sun & Moon...' },
  { id: 'ja', flag: '\uD83C\uDDEF\uD83C\uDDF5', label: 'Japanese', desc: 'SV era, S era, SM era, older sets...' },
  { id: 'th', flag: '\uD83C\uDDF9\uD83C\uDDED', label: 'Thai', desc: 'SC and MA series sets' },
];

export function Settings() {
  const enabledLangs = useSettingsStore(s => s.enabledLangs);
  const toggleLang = useSettingsStore(s => s.toggleLang);

  const enabledCount = Object.values(enabledLangs).filter(Boolean).length;

  return (
    <div className="space-y-6 max-w-xl mx-auto">
      {/* Header */}
      <div>
        <p className="page-section-label mb-1.5">Preferences</p>
        <h1 className="text-3xl font-black flex items-center gap-2.5">
          <SettingsIcon size={26} className="text-amber-400 shrink-0" />
          <span className="text-white">Settings</span>
        </h1>
      </div>

      <div className="gradient-divider" />

      {/* Language Sets */}
      <div
        className="rounded-2xl p-5 space-y-4"
        style={{
          background: 'linear-gradient(145deg, #13132a, #0f0f22)',
          border: '1px solid rgba(139,92,246,0.15)',
        }}
      >
        <div className="flex items-center gap-2.5 mb-1">
          <Globe size={16} className="text-violet-400" />
          <div>
            <p className="text-sm font-bold text-white">Card Languages</p>
            <p className="text-xs text-gray-500">Choose which language sets to show in your library</p>
          </div>
        </div>

        <div className="space-y-2">
          {LANGUAGES.map(({ id, flag, label, desc }) => {
            const enabled = enabledLangs[id];
            const isOnly = enabled && enabledCount === 1;

            return (
              <motion.button
                key={id}
                whileTap={{ scale: 0.98 }}
                onClick={() => toggleLang(id)}
                disabled={isOnly}
                className={`w-full flex items-center gap-3 p-3.5 rounded-xl border transition-all text-left ${
                  enabled
                    ? 'bg-violet-500/8 border-violet-500/25'
                    : 'bg-white/2 border-white/8 opacity-50'
                } ${isOnly ? 'cursor-not-allowed' : 'hover:border-violet-500/40'}`}
              >
                <span className="text-2xl">{flag}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-white">{label}</p>
                  <p className="text-[11px] text-gray-500 truncate">{desc}</p>
                </div>
                {/* Toggle switch */}
                <div
                  className={`relative w-10 h-5.5 rounded-full transition-colors shrink-0 ${
                    enabled ? 'bg-violet-500' : 'bg-white/10'
                  }`}
                  style={{ width: 40, height: 22 }}
                >
                  <motion.div
                    animate={{ x: enabled ? 20 : 2 }}
                    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                    className="absolute top-[2px] w-[18px] h-[18px] rounded-full bg-white shadow-sm"
                  />
                </div>
              </motion.button>
            );
          })}
        </div>

        {enabledCount === 1 && (
          <p className="text-[10px] text-amber-400/70 text-center">
            At least one language must be enabled
          </p>
        )}
      </div>
    </div>
  );
}
