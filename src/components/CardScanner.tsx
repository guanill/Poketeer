import { useRef, useState, useCallback, useEffect, useId } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Camera, Upload, X, Scan, AlertTriangle, CheckCircle,
  Plus, Loader2, ChevronDown, ChevronUp, Search, Wifi,
} from 'lucide-react';
import type { ScanMatch, ScanResult } from '../services/cardScanService';
import { cardScanService } from '../services/cardScanService';
import { catalogService } from '../services/catalogService';
import { useCollectionStore } from '../store/collectionStore';
import { isNativePlatform } from '../utils/platform';
import { setBackendUrl, getBackendUrl } from '../services/nativeScanService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type JobStatus = 'scanning' | 'done' | 'error';

interface ScanJob {
  id: string;
  previewUrl: string;
  status: JobStatus;
  matches: ScanMatch[];
  result: ScanResult | null;
  errorMsg: string;
  expanded: boolean;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 75 ? 'bg-emerald-400' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className={`h-full rounded-full ${color}`}
        />
      </div>
      <span className={`text-xs font-bold tabular-nums ${
        pct >= 75 ? 'text-emerald-400' : pct >= 50 ? 'text-amber-400' : 'text-red-400'
      }`}>{pct}%</span>
    </div>
  );
}

function MethodPill({ method }: { method: ScanMatch['method'] }) {
  const cfg = ({
    ocr:          { label: 'OCR',        cls: 'bg-purple-500/15 text-purple-300  border-purple-500/25'  },
    visual:       { label: 'Visual',     cls: 'bg-blue-500/15   text-blue-300    border-blue-500/25'    },
    'ocr+visual': { label: 'OCR+Visual', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' },
  } as const)[method];
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function MatchRow({ match, rank, isTop }: { match: ScanMatch; rank: number; isTop: boolean }) {
  const owned   = useCollectionStore(s => s.owned);
  const addCard = useCollectionStore(s => s.addCard);
  const removeCard = useCollectionStore(s => s.removeCard);
  const isOwned = (owned[match.id]?.quantity ?? 0) > 0;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.06 }}
      className={`relative flex gap-3 p-3 rounded-xl border transition-colors ${
        isTop
          ? 'bg-amber-400/5 border-amber-400/20'
          : 'bg-white/3 border-white/8 hover:border-white/20'
      }`}
    >
      {isTop && (
        <span className="absolute -top-2 left-3 bg-amber-400 text-black text-[9px] font-black px-2 py-0.5 rounded-full">
          Best match
        </span>
      )}
      <img
        src={match.image_small}
        alt={match.name}
        className="shrink-0 w-14 rounded-lg shadow-md object-cover self-start mt-1"
        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
      />
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-semibold text-white text-sm leading-tight truncate">{match.name}</p>
            <p className="text-xs text-gray-400 truncate">{match.set_name} · #{match.number}</p>
          </div>
          <MethodPill method={match.method} />
        </div>
        <ConfidenceBar value={match.confidence} />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            {match.rarity && <span className="text-[10px] text-amber-400/80 font-medium">{match.rarity}</span>}
            {match.hp    && <span className="text-[10px] text-gray-500">HP {match.hp}</span>}
          </div>
          {isOwned ? (
            <button
              onClick={() => removeCard(match.id)}
              className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/25 transition-colors shrink-0"
            >
              <CheckCircle size={11} />
              In collection
            </button>
          ) : (
            <button
              onClick={() => addCard(match.id)}
              className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full bg-amber-400/10 text-amber-400 border border-amber-400/25 hover:bg-amber-400/20 transition-colors shrink-0"
            >
              <Plus size={11} />
              Add
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// -- Single job card in the queue --
function JobCard({
  job, onToggle, onDismiss,
}: {
  job: ScanJob;
  onToggle: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const topMatch = job.matches[0];

  const needsManual = job.status === 'done' &&
    (job.matches.length === 0 || (topMatch?.confidence ?? 0) < 0.5);
  const rawOcrText = job.result?.ocr_text ?? '';
  const ocrHint = rawOcrText.split('\n[bottom]')[0].split('\n').find(l => l.trim().length > 1) ?? '';
  const [manualQuery, setManualQuery] = useState(ocrHint);
  const [manualMatches, setManualMatches] = useState<ScanMatch[] | null>(null);
  const [searching, setSearching] = useState(false);

  const handleManualSearch = useCallback(async (q: string) => {
    const query = q.trim();
    if (!query) return;
    setSearching(true);
    try {
      const results = await catalogService.fuzzySearchByName(query, 8);
      setManualMatches(results);
    } finally {
      setSearching(false);
    }
  }, []);

  const displayMatches = manualMatches ?? job.matches;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: 60, scale: 0.95 }}
      transition={{ duration: 0.25 }}
      className="rounded-xl overflow-hidden"
      style={{
        background: 'linear-gradient(145deg, #1a1a2e, #13132a)',
        border: `1px solid ${
          job.status === 'scanning' ? 'rgba(245,158,11,0.25)'
          : job.status === 'error'  ? 'rgba(239,68,68,0.25)'
          : 'rgba(255,255,255,0.08)'
        }`,
      }}
    >
      {/* Job header row */}
      <div className="flex items-center gap-3 p-3">
        <div className="relative shrink-0">
          <img
            src={job.previewUrl}
            alt="scan"
            className="w-12 h-16 object-cover rounded-lg"
          />
          <AnimatePresence>
            {job.status === 'scanning' && (
              <motion.div
                key="scan-line"
                className="absolute inset-x-0 h-0.5 bg-amber-400 shadow-[0_0_8px_2px_rgba(245,158,11,0.5)]"
                initial={{ top: '5%', opacity: 0 }}
                animate={{ top: ['5%', '90%', '5%'], opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ repeat: Infinity, duration: 1.6, ease: 'easeInOut' }}
              />
            )}
          </AnimatePresence>
        </div>

        <div className="flex-1 min-w-0">
          <AnimatePresence mode="wait">
          {job.status === 'scanning' ? (
            <motion.div key="scanning" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="flex items-center gap-2 text-amber-400">
              <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }}>
                <Loader2 size={13} />
              </motion.div>
              <span className="text-xs font-semibold">Identifying...</span>
            </motion.div>
          ) : job.status === 'error' ? (
            <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="flex items-center gap-1.5 text-red-400">
              <AlertTriangle size={13} />
              <span className="text-xs font-semibold">Failed</span>
            </motion.div>
          ) : topMatch ? (
            <motion.div key="match" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
              <p className="text-sm font-bold text-white truncate">{topMatch.name}</p>
              <p className="text-xs text-gray-500 truncate">{topMatch.set_name} · #{topMatch.number}</p>
            </motion.div>
          ) : (
            <motion.p key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="text-xs text-gray-500">No matches found</motion.p>
          )}
          </AnimatePresence>

          {job.status === 'done' && topMatch && !needsManual && (
            <div className="flex items-center gap-1.5 mt-1">
              <span className={`text-[10px] font-bold ${
                topMatch.confidence >= 0.75 ? 'text-emerald-400'
                : topMatch.confidence >= 0.5 ? 'text-amber-400'
                : 'text-red-400'
              }`}>
                {Math.round(topMatch.confidence * 100)}% match
              </span>
              {job.matches.length > 1 && (
                <span className="text-[10px] text-gray-600">+{job.matches.length - 1} others</span>
              )}
            </div>
          )}
          {needsManual && (
            <p className="text-[10px] text-amber-400 mt-0.5">Low confidence — search manually</p>
          )}
          {job.status === 'error' && (
            <p className="text-[10px] text-gray-500 mt-0.5 truncate">{job.errorMsg}</p>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {job.status === 'done' && displayMatches.length > 0 && !needsManual && (
            <button
              onClick={() => onToggle(job.id)}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              {job.expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
          <button
            onClick={() => onDismiss(job.id)}
            className="p-1.5 rounded-lg bg-white/5 hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-colors"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Manual search fallback */}
      <AnimatePresence>
        {needsManual && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 border-t border-white/5 pt-3 space-y-2">
              {ocrHint && (
                <p className="text-[10px] text-gray-600 truncate">
                  OCR read: <span className="text-gray-500">{ocrHint}</span>
                </p>
              )}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={manualQuery}
                  onChange={e => setManualQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleManualSearch(manualQuery)}
                  placeholder="Type card name..."
                  className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-gray-600 outline-none focus:border-purple-500/50"
                />
                <button
                  onClick={() => handleManualSearch(manualQuery)}
                  disabled={searching}
                  className="px-3 py-1.5 rounded-lg bg-purple-600/70 hover:bg-purple-600 text-white text-xs font-semibold flex items-center gap-1 disabled:opacity-50 transition-colors"
                >
                  {searching
                    ? <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }}><Loader2 size={12} /></motion.div>
                    : <Search size={12} />}
                  Search
                </button>
              </div>
              {manualMatches && manualMatches.length === 0 && (
                <p className="text-[10px] text-gray-600 text-center py-1">No results</p>
              )}
              {manualMatches && manualMatches.length > 0 && (
                <div className="space-y-2">
                  {manualMatches.map((m, i) => (
                    <MatchRow key={m.id} match={m} rank={i} isTop={i === 0} />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Expanded match list */}
      <AnimatePresence>
        {job.expanded && displayMatches.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-2 border-t border-white/5 pt-3">
              {displayMatches.map((m, i) => (
                <MatchRow key={m.id} match={m} rank={i} isTop={i === 0} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type UIMode = 'idle' | 'camera' | 'error';

export function CardScanner() {
  const uid = useId();
  const [mode, setMode]           = useState<UIMode>('idle');
  const [jobs, setJobs]           = useState<ScanJob[]>([]);
  const [errorMsg, setErrorMsg]   = useState('');
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [cameraSupported, setCameraSupported] = useState<boolean | null>(null);
  const [shotFlash, setShotFlash] = useState(false);
  const [serverUrl, setServerUrl] = useState(() => getBackendUrl() ?? '');
  const [serverConnected, setServerConnected] = useState<boolean | null>(null);

  const videoRef    = useRef<HTMLVideoElement>(null);
  const inlineVideoRef = useRef<HTMLVideoElement>(null);
  const inlineStreamRef = useRef<MediaStream | null>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const jobSeqRef   = useRef(0);

  const [isMobile] = useState(() =>
    typeof window !== 'undefined' &&
    ('ontouchstart' in window || window.innerWidth < 640)
  );

  useEffect(() => {
    cardScanService.checkHealth().then(setBackendOk);
    const supported =
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function';
    setCameraSupported(supported);
  }, []);

  // Auto-start inline camera on mobile
  useEffect(() => {
    if (!isMobile || !cameraSupported) return;
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: { ideal: 'environment' } },
        });
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }
        inlineStreamRef.current = stream;
        if (inlineVideoRef.current) inlineVideoRef.current.srcObject = stream;
      } catch { /* camera denied — upload fallback visible */ }
    })();
    return () => {
      cancelled = true;
      inlineStreamRef.current?.getTracks().forEach(t => t.stop());
      inlineStreamRef.current = null;
    };
  }, [isMobile, cameraSupported]);

  const connectToServer = useCallback(async () => {
    const url = serverUrl.trim().replace(/\/+$/, '');
    if (!url) {
      setBackendUrl(null);
      setServerConnected(null);
      return;
    }
    try {
      const res = await fetch(`${url}/health`, {
        signal: AbortSignal.timeout(8000),
        mode: 'cors',
      });
      if (res.ok) {
        setBackendUrl(url);
        setServerConnected(true);
      } else {
        setServerConnected(false);
      }
    } catch {
      setServerConnected(false);
    }
  }, [serverUrl]);

  useEffect(() => {
    if (mode === 'camera' && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [mode]);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  }, []);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: { ideal: 'environment' } },
      });
      streamRef.current = stream;
      setMode('camera');
    } catch {
      setErrorMsg('Camera access denied or no camera found. Use the upload option instead.');
      setMode('error');
    }
  }, []);

  const queueScan = useCallback(async (blob: Blob, previewUrl: string) => {
    const id = `${uid}-${++jobSeqRef.current}`;
    setJobs(prev => [{
      id, previewUrl, status: 'scanning',
      matches: [], result: null, errorMsg: '', expanded: false,
    }, ...prev]);

    try {
      const result = await cardScanService.scanCard(blob, 5);
      setJobs(prev => prev.map(j =>
        j.id === id
          ? { ...j, status: 'done', matches: result.matches, result, expanded: result.matches.length > 0 }
          : j
      ));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scan failed. Is the backend running?';
      setJobs(prev => prev.map(j =>
        j.id === id ? { ...j, status: 'error', errorMsg: msg } : j
      ));
    }
  }, [uid]);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    setShotFlash(true);
    setTimeout(() => setShotFlash(false), 180);

    const canvas = document.createElement('canvas');
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')!.drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      queueScan(blob, url);
    }, 'image/jpeg', 0.92);
  }, [queueScan]);

  const captureInlineFrame = useCallback(() => {
    const video = inlineVideoRef.current;
    if (!video) return;
    setShotFlash(true);
    setTimeout(() => setShotFlash(false), 180);

    const canvas = document.createElement('canvas');
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')!.drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      queueScan(blob, url);
    }, 'image/jpeg', 0.92);
  }, [queueScan]);

  const loadFiles = useCallback((files: FileList | File[]) => {
    Array.from(files).forEach(file => {
      if (!file.type.startsWith('image/')) return;
      const url = URL.createObjectURL(file);
      queueScan(file, url);
    });
  }, [queueScan]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      loadFiles(e.target.files);
      e.target.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length) loadFiles(files);
  };

  const toggleJob  = (id: string) =>
    setJobs(prev => prev.map(j => j.id === id ? { ...j, expanded: !j.expanded } : j));
  const dismissJob = (id: string) =>
    setJobs(prev => prev.filter(j => j.id !== id));
  const clearDone  = () =>
    setJobs(prev => prev.filter(j => j.status === 'scanning'));

  const closeCameraAndGoIdle = useCallback(() => {
    stopCamera();
    setMode('idle');
  }, [stopCamera]);

  useEffect(() => () => {
    stopCamera();
    inlineStreamRef.current?.getTracks().forEach(t => t.stop());
  }, [stopCamera]);

  const scanningCount = jobs.filter(j => j.status === 'scanning').length;
  const doneCount     = jobs.filter(j => j.status === 'done').length;

  // Batch add
  const batchOwned = useCollectionStore(s => s.owned);
  const batchAddCard = useCollectionStore(s => s.addCard);
  const [batchAddResult, setBatchAddResult] = useState<{ count: number } | null>(null);

  const addableJobs = jobs.filter(j =>
    j.status === 'done' &&
    j.matches.length > 0 &&
    j.matches[0].confidence >= 0.5 &&
    !(batchOwned[j.matches[0].id]?.quantity > 0)
  );

  const handleAddAll = useCallback(() => {
    const currentOwned = useCollectionStore.getState().owned;
    let count = 0;
    for (const job of addableJobs) {
      const topMatch = job.matches[0];
      if (!(currentOwned[topMatch.id]?.quantity > 0)) {
        batchAddCard(topMatch.id);
        count++;
      }
    }
    setBatchAddResult({ count });
    setTimeout(() => setBatchAddResult(null), 3000);
  }, [addableJobs, batchAddCard]);

  return (
    <>
      {/* ============================================================== */}
      {/* FULLSCREEN CAMERA OVERLAY                                       */}
      {/* ============================================================== */}
      <AnimatePresence>
        {mode === 'camera' && (
          <motion.div
            key="camera-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black flex flex-col"
          >
            {/* Video fills the screen */}
            <div className="relative flex-1 overflow-hidden">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="absolute inset-0 w-full h-full object-cover"
              />

              {/* Card outline guide — large, centered, card-shaped (2.5:3.5 ratio) */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div
                  className="relative rounded-2xl border-2 border-amber-400/80"
                  style={{
                    width: 'min(72vw, 320px)',
                    aspectRatio: '2.5 / 3.5',
                    boxShadow: '0 0 0 9999px rgba(0,0,0,0.5), inset 0 0 40px rgba(245,158,11,0.08)',
                  }}
                >
                  {/* Corner accents */}
                  <div className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-amber-400 rounded-tl-2xl" />
                  <div className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-amber-400 rounded-tr-2xl" />
                  <div className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-amber-400 rounded-bl-2xl" />
                  <div className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-amber-400 rounded-br-2xl" />

                  {/* Scanning sweep line */}
                  <motion.div
                    className="absolute inset-x-2 h-0.5 rounded-full"
                    style={{ background: 'linear-gradient(90deg, transparent, #F59E0B, transparent)' }}
                    animate={{ top: ['5%', '92%', '5%'] }}
                    transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
                  />
                </div>
              </div>

              {/* Hint text */}
              <div className="absolute top-0 inset-x-0 pt-14 flex justify-center pointer-events-none">
                <span className="text-white/60 text-xs font-semibold bg-black/40 px-3 py-1.5 rounded-full backdrop-blur-sm">
                  Align card within the frame
                </span>
              </div>

              {/* Shot flash */}
              <AnimatePresence>
                {shotFlash && (
                  <motion.div
                    key="flash"
                    initial={{ opacity: 0.8 }}
                    animate={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="absolute inset-0 bg-white pointer-events-none"
                  />
                )}
              </AnimatePresence>

              {/* Scanning count badge — top right */}
              {scanningCount > 0 && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute top-14 right-4 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm px-3 py-1.5 rounded-full"
                >
                  <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }}>
                    <Loader2 size={12} className="text-amber-400" />
                  </motion.div>
                  <span className="text-xs text-amber-400 font-bold">{scanningCount} scanning</span>
                </motion.div>
              )}
            </div>

            {/* Bottom controls bar */}
            <div
              className="shrink-0 flex items-center justify-between px-6 py-5"
              style={{
                background: 'linear-gradient(to top, rgba(0,0,0,0.95), rgba(0,0,0,0.7))',
                paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 1.25rem)',
              }}
            >
              {/* Close */}
              <button
                onClick={closeCameraAndGoIdle}
                className="w-12 h-12 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-colors"
              >
                <X size={22} />
              </button>

              {/* Shutter */}
              <motion.button
                whileTap={{ scale: 0.85 }}
                onClick={captureFrame}
                className="w-18 h-18 rounded-full flex items-center justify-center"
                style={{
                  background: 'linear-gradient(135deg, #F59E0B, #d97706)',
                  boxShadow: '0 0 30px rgba(245,158,11,0.4), inset 0 2px 0 rgba(255,255,255,0.2)',
                }}
              >
                <div className="w-14 h-14 rounded-full border-2 border-black/20 flex items-center justify-center">
                  <Camera size={24} className="text-black" />
                </div>
              </motion.button>

              {/* Upload from gallery */}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-12 h-12 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-colors"
              >
                <Upload size={20} />
              </button>
            </div>

            {/* Latest result toast (slides up from bottom when a scan finishes while camera is open) */}
            <AnimatePresence>
              {jobs.length > 0 && jobs[0].status === 'done' && jobs[0].matches.length > 0 && (
                <motion.div
                  initial={{ y: 100, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: 100, opacity: 0 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 25 }}
                  className="absolute bottom-28 left-4 right-4 z-10"
                  style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
                >
                  <div
                    className="flex items-center gap-3 p-3 rounded-xl backdrop-blur-md"
                    style={{ background: 'rgba(26,26,46,0.92)', border: '1px solid rgba(245,158,11,0.25)' }}
                  >
                    <img
                      src={jobs[0].matches[0].image_small}
                      alt=""
                      className="w-10 h-14 object-cover rounded-lg shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-white truncate">{jobs[0].matches[0].name}</p>
                      <p className="text-[10px] text-emerald-400 font-bold">
                        {Math.round(jobs[0].matches[0].confidence * 100)}% match
                      </p>
                    </div>
                    <button
                      onClick={() => { addCardFromMatch(jobs[0].matches[0]); }}
                      className="shrink-0 px-3 py-1.5 rounded-lg bg-amber-400/15 text-amber-400 text-xs font-bold border border-amber-400/25 hover:bg-amber-400/25 transition-colors"
                    >
                      <Plus size={12} className="inline mr-1" />
                      Add
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ============================================================== */}
      {/* INLINE CONTENT (idle / error / scan queue)                      */}
      {/* ============================================================== */}
      <div className="max-w-xl mx-auto space-y-4">

        {/* Backend offline banner */}
        <AnimatePresence>
          {backendOk === false && mode !== 'camera' && (
            <motion.div
              initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="flex items-start gap-3 p-3 rounded-xl bg-orange-500/10 border border-orange-500/30 text-orange-300 text-xs">
                <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                <span>
                  <strong>Scanner backend offline.</strong> Run:{' '}
                  <code className="bg-black/30 px-1 rounded">cd backend &amp;&amp; python main.py</code>
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Server connection (native only) */}
        {isNativePlatform() && mode !== 'camera' && (
          <div className="p-3 rounded-xl bg-white/3 border border-white/8 space-y-2">
            <div className="flex items-center gap-2">
              <Wifi size={13} className={serverConnected ? 'text-emerald-400' : 'text-gray-500'} />
              <span className="text-xs font-semibold text-gray-300">PC Scanner Server</span>
              {serverConnected === true && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 font-bold">Connected</span>
              )}
              {serverConnected === false && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/25 font-bold">Unreachable</span>
              )}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={serverUrl}
                onChange={e => setServerUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && connectToServer()}
                placeholder="http://192.168.1.x:8000"
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-gray-600 outline-none focus:border-amber-400/50"
              />
              <button
                onClick={connectToServer}
                className="px-3 py-1.5 rounded-lg bg-amber-400/10 hover:bg-amber-400/20 text-amber-400 text-xs font-semibold border border-amber-400/25 transition-colors"
              >
                Connect
              </button>
            </div>
          </div>
        )}

        {/* ---- MOBILE: inline camera feed always visible ---- */}
        {isMobile && mode !== 'error' && (
          <div className="space-y-3">
            {cameraSupported !== false ? (
              <div className="relative rounded-2xl overflow-hidden border border-amber-400/20"
                style={{ background: '#000' }}
              >
                <video
                  ref={inlineVideoRef}
                  autoPlay
                  playsInline
                  muted
                  className="w-full aspect-3/4 object-cover"
                />

                {/* Card outline guide */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div
                    className="relative rounded-xl border-2 border-amber-400/60"
                    style={{
                      width: '65%',
                      aspectRatio: '2.5 / 3.5',
                      boxShadow: '0 0 0 9999px rgba(0,0,0,0.35)',
                    }}
                  >
                    <div className="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-amber-400 rounded-tl-xl" />
                    <div className="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-amber-400 rounded-tr-xl" />
                    <div className="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-amber-400 rounded-bl-xl" />
                    <div className="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-amber-400 rounded-br-xl" />
                    <motion.div
                      className="absolute inset-x-2 h-0.5 rounded-full"
                      style={{ background: 'linear-gradient(90deg, transparent, #F59E0B, transparent)' }}
                      animate={{ top: ['5%', '92%', '5%'] }}
                      transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
                    />
                  </div>
                </div>

                {/* Shot flash */}
                <AnimatePresence>
                  {shotFlash && (
                    <motion.div
                      key="flash"
                      initial={{ opacity: 0.8 }}
                      animate={{ opacity: 0 }}
                      transition={{ duration: 0.18 }}
                      className="absolute inset-0 bg-white pointer-events-none"
                    />
                  )}
                </AnimatePresence>

                {/* Capture button */}
                <div className="absolute bottom-4 inset-x-0 flex justify-center">
                  <motion.button
                    whileTap={{ scale: 0.85 }}
                    onClick={captureInlineFrame}
                    className="w-16 h-16 rounded-full flex items-center justify-center"
                    style={{
                      background: 'linear-gradient(135deg, #F59E0B, #d97706)',
                      boxShadow: '0 0 24px rgba(245,158,11,0.4), inset 0 2px 0 rgba(255,255,255,0.2)',
                    }}
                  >
                    <div className="w-12 h-12 rounded-full border-2 border-black/20 flex items-center justify-center">
                      <Camera size={22} className="text-black" />
                    </div>
                  </motion.button>
                </div>

                {/* Scanning badge */}
                {scanningCount > 0 && (
                  <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm px-2.5 py-1 rounded-full">
                    <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.9, ease: 'linear' }}>
                      <Loader2 size={11} className="text-amber-400" />
                    </motion.div>
                    <span className="text-[10px] text-amber-400 font-bold">{scanningCount}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="w-full flex flex-col items-center justify-center gap-3 py-14 rounded-2xl border border-white/8 bg-white/2">
                <Camera size={30} className="text-gray-600" />
                <p className="text-xs text-gray-600">Camera unavailable — use upload below</p>
              </div>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-white/8 text-gray-400 hover:text-white hover:border-white/15 transition-colors"
            >
              <Upload size={14} />
              <span className="text-xs font-medium">Upload from gallery</span>
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleFileChange} />
          </div>
        )}

        {/* ---- DESKTOP: upload + drag/drop only ---- */}
        {!isMobile && mode === 'idle' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
            <div
              onDrop={handleDrop}
              onDragOver={e => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className="flex flex-col items-center justify-center gap-4 py-16 rounded-2xl border-2 border-dashed border-white/10 hover:border-violet-500/30 hover:bg-violet-500/3 transition-all cursor-pointer group"
            >
              <div className="w-14 h-14 rounded-full bg-violet-500/15 border border-violet-500/25 flex items-center justify-center group-hover:scale-110 group-hover:bg-violet-500/25 transition-all">
                <Upload size={24} className="text-violet-400" />
              </div>
              <div className="text-center">
                <p className="font-bold text-white text-sm">Drop card images here</p>
                <p className="text-xs text-gray-500 mt-1">or click to browse from your files</p>
              </div>
            </div>
            <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleFileChange} />
          </motion.div>
        )}

        {/* ERROR */}
        {mode === 'error' && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="w-14 h-14 rounded-full bg-red-500/10 border border-red-500/25 flex items-center justify-center">
              <AlertTriangle size={22} className="text-red-400" />
            </div>
            <div>
              <p className="font-semibold text-white">Camera error</p>
              <p className="text-sm text-gray-400 mt-1 max-w-xs">{errorMsg}</p>
            </div>
            <button onClick={() => setMode('idle')} className="px-5 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300 hover:bg-white/10 transition-colors">
              Go back
            </button>
          </motion.div>
        )}

        {/* SCAN QUEUE */}
        <AnimatePresence>
          {jobs.length > 0 && mode !== 'camera' && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Scan size={14} className="text-amber-400" />
                  <span className="text-sm font-bold text-white">Scan Results</span>
                  {scanningCount > 0 && (
                    <span className="text-xs px-2 py-0.5 rounded-full font-bold"
                      style={{ background: 'rgba(245,158,11,0.15)', color: '#fcd34d' }}>
                      {scanningCount} scanning
                    </span>
                  )}
                  {doneCount > 0 && (
                    <span className="text-xs px-2 py-0.5 rounded-full font-bold"
                      style={{ background: 'rgba(52,211,153,0.12)', color: '#6ee7b7' }}>
                      {doneCount} done
                    </span>
                  )}
                </div>
                {doneCount > 0 && (
                  <button onClick={clearDone} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
                    Clear done
                  </button>
                )}
              </div>

              {/* Batch add bar */}
              <AnimatePresence>
                {addableJobs.length > 1 && !batchAddResult && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="flex items-center justify-between p-3 rounded-xl bg-emerald-500/8 border border-emerald-500/20">
                      <span className="text-sm font-bold text-white">
                        {addableJobs.length} new cards found
                      </span>
                      <motion.button
                        whileTap={{ scale: 0.95 }}
                        onClick={handleAddAll}
                        className="px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 text-xs font-bold border border-emerald-500/30 hover:bg-emerald-500/30 transition-colors flex items-center gap-1.5"
                      >
                        <Plus size={13} />
                        Add All
                      </motion.button>
                    </div>
                  </motion.div>
                )}
                {batchAddResult && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/25 text-center"
                  >
                    <span className="text-sm font-bold text-emerald-400">
                      {batchAddResult.count} card{batchAddResult.count !== 1 ? 's' : ''} added to collection
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="space-y-2">
                <AnimatePresence initial={false}>
                  {jobs.map(job => (
                    <JobCard key={job.id} job={job} onToggle={toggleJob} onDismiss={dismissJob} />
                  ))}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}

// Helper used in the camera toast
function addCardFromMatch(match: ScanMatch) {
  useCollectionStore.getState().addCard(match.id);
}
