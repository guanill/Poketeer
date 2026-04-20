import { create } from 'zustand';
import type { ScanMatch, ScanResult, ScanLanguage } from '../services/cardScanService';

export type JobStatus = 'scanning' | 'done' | 'error';

export interface ScanJob {
  id: string;
  previewUrl: string;
  status: JobStatus;
  matches: ScanMatch[];
  result: ScanResult | null;
  errorMsg: string;
  expanded: boolean;
}

interface ScanStore {
  jobs: ScanJob[];
  scanLang: ScanLanguage;
  jobSeq: number;
  isOpen: boolean;

  setScanLang: (lang: ScanLanguage) => void;
  openScanner: () => void;
  closeScanner: () => void;
  nextJobId: (prefix: string) => string;
  addJob: (job: ScanJob) => void;
  updateJob: (id: string, patch: Partial<ScanJob>) => void;
  toggleJob: (id: string) => void;
  dismissJob: (id: string) => void;
  clearDone: () => void;
}

export const useScanStore = create<ScanStore>((set, get) => ({
  jobs: [],
  scanLang: 'en',
  jobSeq: 0,
  isOpen: false,

  setScanLang: (lang) => set({ scanLang: lang }),

  openScanner: () => set({ isOpen: true }),
  closeScanner: () => set({ isOpen: false }),

  nextJobId: (prefix) => {
    const seq = get().jobSeq + 1;
    set({ jobSeq: seq });
    return `${prefix}-${seq}`;
  },

  addJob: (job) => set((s) => ({ jobs: [job, ...s.jobs] })),

  updateJob: (id, patch) =>
    set((s) => ({
      jobs: s.jobs.map((j) => (j.id === id ? { ...j, ...patch } : j)),
    })),

  toggleJob: (id) =>
    set((s) => ({
      jobs: s.jobs.map((j) =>
        j.id === id ? { ...j, expanded: !j.expanded } : j,
      ),
    })),

  dismissJob: (id) =>
    set((s) => {
      const job = s.jobs.find((j) => j.id === id);
      if (job?.result?.cropNameUrl) URL.revokeObjectURL(job.result.cropNameUrl);
      if (job?.result?.cropNumberUrl) URL.revokeObjectURL(job.result.cropNumberUrl);
      if (job?.previewUrl) URL.revokeObjectURL(job.previewUrl);
      return { jobs: s.jobs.filter((j) => j.id !== id) };
    }),

  clearDone: () =>
    set((s) => {
      for (const j of s.jobs) {
        if (j.status !== 'scanning') {
          if (j.result?.cropNameUrl) URL.revokeObjectURL(j.result.cropNameUrl);
          if (j.result?.cropNumberUrl) URL.revokeObjectURL(j.result.cropNumberUrl);
          if (j.previewUrl) URL.revokeObjectURL(j.previewUrl);
        }
      }
      return { jobs: s.jobs.filter((j) => j.status === 'scanning') };
    }),
}));
