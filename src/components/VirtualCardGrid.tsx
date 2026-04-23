import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useWindowVirtualizer } from '@tanstack/react-virtual';
import type { PokemonCard } from '../types';
import { CardItem } from './CardItem';

type Breakpoint = { min: number; cols: number };

// Column counts mirror the Tailwind classes used by the non-virtualized grids:
// grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8
const DEFAULT_BREAKPOINTS: ReadonlyArray<Breakpoint> = [
  { min: 1280, cols: 8 },
  { min: 1024, cols: 6 },
  { min: 768, cols: 5 },
  { min: 640, cols: 4 },
  { min: 0, cols: 3 },
];

function columnsForWidth(w: number, bps: ReadonlyArray<Breakpoint>): number {
  return bps.find(b => w >= b.min)!.cols;
}

function useColumnCount(bps: ReadonlyArray<Breakpoint>): number {
  const [cols, setCols] = useState(() =>
    typeof window === 'undefined' ? bps[bps.length - 1].cols : columnsForWidth(window.innerWidth, bps),
  );
  useEffect(() => {
    const onResize = () => setCols(columnsForWidth(window.innerWidth, bps));
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [bps]);
  return cols;
}

interface VirtualCardGridProps {
  cards: PokemonCard[];
  onViewDetails?: (card: PokemonCard) => void;
  /** Initial row-height guess; the virtualizer measures real heights afterwards. */
  estimatedRowHeight?: number;
  /** Fires when the user scrolls within `endReachedThreshold` rows of the end. */
  onEndReached?: () => void;
  endReachedThreshold?: number;
  /** Override responsive column counts. Sorted largest-to-smallest min width. */
  breakpoints?: ReadonlyArray<Breakpoint>;
  gap?: string;
}

export function VirtualCardGrid({
  cards,
  onViewDetails,
  estimatedRowHeight = 280,
  onEndReached,
  endReachedThreshold = 3,
  breakpoints = DEFAULT_BREAKPOINTS,
  gap = '0.75rem',
}: VirtualCardGridProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const cols = useColumnCount(breakpoints);
  const rowCount = Math.ceil(cards.length / cols);

  const [scrollMargin, setScrollMargin] = useState(0);
  useLayoutEffect(() => {
    if (!parentRef.current) return;
    const update = () => {
      const rect = parentRef.current?.getBoundingClientRect();
      if (rect) setScrollMargin(rect.top + window.scrollY);
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [cols]);

  const virtualizer = useWindowVirtualizer({
    count: rowCount,
    estimateSize: () => estimatedRowHeight,
    overscan: 3,
    scrollMargin,
  });

  const items = virtualizer.getVirtualItems();
  const lastIndex = items[items.length - 1]?.index ?? -1;

  useEffect(() => {
    if (!onEndReached) return;
    if (rowCount === 0) return;
    if (lastIndex >= rowCount - endReachedThreshold) onEndReached();
  }, [lastIndex, rowCount, endReachedThreshold, onEndReached]);

  return (
    <div
      ref={parentRef}
      style={{ position: 'relative', height: `${virtualizer.getTotalSize()}px` }}
    >
      {items.map(item => {
        const start = item.index * cols;
        const rowCards = cards.slice(start, start + cols);
        return (
          <div
            key={item.key}
            data-index={item.index}
            ref={virtualizer.measureElement}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              transform: `translateY(${item.start - virtualizer.options.scrollMargin}px)`,
              display: 'grid',
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
              gap,
              paddingBottom: gap,
            }}
          >
            {rowCards.map(card => (
              <CardItem key={card.id} card={card} onViewDetails={onViewDetails} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
