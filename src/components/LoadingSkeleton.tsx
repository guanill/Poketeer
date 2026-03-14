import { motion } from 'framer-motion';

interface SkeletonProps {
  count?: number;
  type?: 'card' | 'set' | 'stat' | 'list';
}

function SkeletonBox({ className }: { className: string }) {
  return (
    <div className={`shimmer bg-white/5 rounded-lg ${className}`} />
  );
}

function CardSkeleton() {
  return (
    <div className="rounded-xl overflow-hidden bg-[#1a1a2e] border border-white/5 p-3">
      <SkeletonBox className="w-12 h-4 mx-auto mb-3" />
      <SkeletonBox className="aspect-2.5/3.5 max-w-35 mx-auto mb-2" />
      <SkeletonBox className="h-3 w-3/4 mx-auto mb-1" />
      <SkeletonBox className="h-2 w-1/2 mx-auto" />
    </div>
  );
}

function SetSkeleton() {
  return (
    <div className="rounded-xl bg-[#1a1a2e] border border-white/5 p-4">
      <div className="flex items-start gap-3">
        <SkeletonBox className="w-12 h-12 rounded-lg shrink-0" />
        <div className="flex-1">
          <SkeletonBox className="h-4 w-3/4 mb-2" />
          <SkeletonBox className="h-3 w-1/2 mb-2" />
          <SkeletonBox className="h-2 w-1/3" />
        </div>
        <SkeletonBox className="w-12 h-12 rounded-full shrink-0" />
      </div>
    </div>
  );
}

function StatSkeleton() {
  return (
    <div className="rounded-xl bg-[#1a1a2e] border border-white/5 p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <SkeletonBox className="h-3 w-1/3 mb-2" />
          <SkeletonBox className="h-8 w-1/2 mb-1" />
          <SkeletonBox className="h-2 w-2/3" />
        </div>
        <SkeletonBox className="w-10 h-10 rounded-xl" />
      </div>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="rounded-xl bg-[#1a1a2e] border border-white/5 p-4 flex items-center gap-3">
      <SkeletonBox className="w-10 h-14 rounded-lg shrink-0" />
      <div className="flex-1">
        <SkeletonBox className="h-3 w-2/3 mb-2" />
        <SkeletonBox className="h-2 w-1/3" />
      </div>
      <SkeletonBox className="w-16 h-6 rounded-full" />
    </div>
  );
}

export function LoadingSkeleton({ count = 6, type = 'card' }: SkeletonProps) {
  const skeletonMap = {
    card: CardSkeleton,
    set: SetSkeleton,
    stat: StatSkeleton,
    list: ListSkeleton,
  };
  const Component = skeletonMap[type];

  const gridClass = {
    card: 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3',
    set: 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4',
    stat: 'grid grid-cols-2 md:grid-cols-4 gap-4',
    list: 'flex flex-col gap-3',
  }[type];

  return (
    <div className={gridClass}>
      {Array.from({ length: count }).map((_, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * 0.05 }}
        >
          <Component />
        </motion.div>
      ))}
    </div>
  );
}
