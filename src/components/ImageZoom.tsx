import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

interface ImageZoomProps {
  src: string | null;
  alt?: string;
  onClose: () => void;
}

const MIN_SCALE = 1;
const MAX_SCALE = 6;

export function ImageZoom({ src, alt, onClose }: ImageZoomProps) {
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const imgRef = useRef<HTMLImageElement | null>(null);
  const pinchStart = useRef<{ dist: number; scale: number } | null>(null);
  const lastPan = useRef<{ x: number; y: number } | null>(null);

  // Reset transform whenever a new image opens
  useEffect(() => {
    if (src) {
      setScale(1);
      setPos({ x: 0, y: 0 });
    }
  }, [src]);

  // ESC to close
  useEffect(() => {
    if (!src) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === '+' || e.key === '=') setScale(s => Math.min(MAX_SCALE, s + 0.5));
      if (e.key === '-') setScale(s => Math.max(MIN_SCALE, s - 0.5));
      if (e.key === '0') { setScale(1); setPos({ x: 0, y: 0 }); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [src, onClose]);

  const clampPos = (s: number, p: { x: number; y: number }) => {
    const img = imgRef.current;
    if (!img) return p;
    const w = img.clientWidth * s;
    const h = img.clientHeight * s;
    const maxX = Math.max(0, (w - window.innerWidth) / 2 + 20);
    const maxY = Math.max(0, (h - window.innerHeight) / 2 + 20);
    return { x: Math.max(-maxX, Math.min(maxX, p.x)), y: Math.max(-maxY, Math.min(maxY, p.y)) };
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = -e.deltaY * 0.0025;
    setScale(s => {
      const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, s + delta * s));
      if (next === 1) setPos({ x: 0, y: 0 });
      return next;
    });
  };

  const onDoubleClick = () => {
    if (scale > 1) {
      setScale(1);
      setPos({ x: 0, y: 0 });
    } else {
      setScale(2.5);
    }
  };

  // Touch: two-finger pinch + one-finger pan
  const touchDist = (t: React.TouchList) => {
    const dx = t[0].clientX - t[1].clientX;
    const dy = t[0].clientY - t[1].clientY;
    return Math.hypot(dx, dy);
  };

  const onTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      pinchStart.current = { dist: touchDist(e.touches), scale };
      lastPan.current = null;
    } else if (e.touches.length === 1 && scale > 1) {
      lastPan.current = { x: e.touches[0].clientX - pos.x, y: e.touches[0].clientY - pos.y };
      pinchStart.current = null;
    }
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 2 && pinchStart.current) {
      e.preventDefault();
      const d = touchDist(e.touches);
      const ratio = d / pinchStart.current.dist;
      const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, pinchStart.current.scale * ratio));
      setScale(next);
      if (next === 1) setPos({ x: 0, y: 0 });
    } else if (e.touches.length === 1 && lastPan.current && scale > 1) {
      e.preventDefault();
      const nx = e.touches[0].clientX - lastPan.current.x;
      const ny = e.touches[0].clientY - lastPan.current.y;
      setPos(p => clampPos(scale, { x: nx, y: ny }) || p);
    }
  };

  const onTouchEnd = () => {
    pinchStart.current = null;
    lastPan.current = null;
  };

  // Mouse drag pan when zoomed
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const onMouseDown = (e: React.MouseEvent) => {
    if (scale <= 1) return;
    dragStart.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragStart.current) return;
    setPos(clampPos(scale, { x: e.clientX - dragStart.current.x, y: e.clientY - dragStart.current.y }));
  };
  const onMouseUp = () => { dragStart.current = null; };

  return (
    <AnimatePresence>
      {src && (
        <motion.div
          key="zoom-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-[60] flex items-center justify-center select-none"
          style={{ background: 'rgba(0,0,0,0.94)', backdropFilter: 'blur(12px)', touchAction: 'none' }}
          onClick={onClose}
          onWheel={onWheel}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        >
          <motion.img
            ref={imgRef}
            key="zoom-img"
            src={src}
            alt={alt}
            draggable={false}
            initial={{ scale: 0.92, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.96, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 240, damping: 28 }}
            onDoubleClick={(e) => { e.stopPropagation(); onDoubleClick(); }}
            onClick={(e) => e.stopPropagation()}
            className="max-w-[95vw] max-h-[92vh] rounded-xl"
            style={{
              transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})`,
              transition: dragStart.current || pinchStart.current || lastPan.current ? 'none' : 'transform 0.18s ease-out',
              cursor: scale > 1 ? (dragStart.current ? 'grabbing' : 'grab') : 'zoom-in',
              willChange: 'transform',
              boxShadow: '0 40px 120px rgba(0,0,0,0.75)',
            }}
          />

          {/* Controls */}
          <div
            className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-2 py-1.5 rounded-full z-[61]"
            style={{
              background: 'rgba(20,20,42,0.85)',
              border: '1px solid rgba(245,158,11,0.25)',
              backdropFilter: 'blur(10px)',
              boxShadow: '0 6px 22px rgba(0,0,0,0.55)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setScale(s => Math.max(MIN_SCALE, s - 0.5))}
              disabled={scale <= MIN_SCALE}
              className="p-2 rounded-full hover:bg-white/10 text-gray-300 disabled:opacity-30 transition-colors"
              aria-label="Zoom out"
            >
              <ZoomOut size={16} />
            </button>
            <span className="text-[11px] font-bold tabular-nums text-amber-300 min-w-[3ch] text-center">
              {Math.round(scale * 100)}%
            </span>
            <button
              onClick={() => setScale(s => Math.min(MAX_SCALE, s + 0.5))}
              disabled={scale >= MAX_SCALE}
              className="p-2 rounded-full hover:bg-white/10 text-gray-300 disabled:opacity-30 transition-colors"
              aria-label="Zoom in"
            >
              <ZoomIn size={16} />
            </button>
            <div className="w-px h-4 bg-white/10 mx-0.5" />
            <button
              onClick={() => { setScale(1); setPos({ x: 0, y: 0 }); }}
              className="p-2 rounded-full hover:bg-white/10 text-gray-300 transition-colors"
              aria-label="Reset zoom"
            >
              <Maximize2 size={14} />
            </button>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 z-[61] p-2.5 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
