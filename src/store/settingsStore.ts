import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Lang = 'en' | 'ja' | 'th';

interface SettingsStore {
  enabledLangs: Record<Lang, boolean>;
  toggleLang: (lang: Lang) => void;
  isLangEnabled: (lang: Lang) => boolean;
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set, get) => ({
      enabledLangs: { en: true, ja: true, th: true },

      toggleLang: (lang) =>
        set((state) => {
          const next = { ...state.enabledLangs, [lang]: !state.enabledLangs[lang] };
          // Prevent disabling all languages — keep at least one enabled
          if (!next.en && !next.ja && !next.th) return state;
          return { enabledLangs: next };
        }),

      isLangEnabled: (lang) => get().enabledLangs[lang],
    }),
    { name: 'poketeer-settings' },
  ),
);
