import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: ReactNode;
  color: string;
  delay?: number;
  trend?: { value: number; label: string };
}

export function StatCard({ title, value, subtitle, icon, color, delay = 0, trend }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, type: 'spring', stiffness: 200, damping: 20 }}
      whileHover={{ y: -4, scale: 1.02 }}
      className="relative rounded-2xl p-4 overflow-hidden"
      style={{
        background: 'linear-gradient(145deg, #1c1c38 0%, #12122a 100%)',
        border: `1px solid ${color}35`,
        boxShadow: `0 4px 28px ${color}18, inset 0 1px 0 rgba(255,255,255,0.06)`,
      }}
    >
      {/* Background glow orb */}
      <div
        className="absolute top-0 right-0 w-28 h-28 rounded-full pointer-events-none"
        style={{
          background: `radial-gradient(circle, ${color}25, transparent 70%)`,
          transform: 'translate(35%, -35%)',
        }}
      />
      {/* Decorative orb ring */}
      <div
        className="orb-ring"
        style={{
          width: 80, height: 80,
          right: -20, bottom: -30,
          borderColor: `${color}10`,
        }}
      />

      {/* Top accent line */}
      <div
        className="absolute top-0 left-4 right-4 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${color}50, transparent)` }}
      />

      <div className="flex items-start justify-between relative">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-widest font-bold">{title}</p>
          <motion.p
            className="text-2xl font-black text-white mt-1 tracking-tight"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: delay + 0.2 }}
          >
            {value}
          </motion.p>
          {subtitle && (
            <p className="text-xs text-gray-500 mt-0.5 font-semibold">{subtitle}</p>
          )}
          {trend && (
            <div className={`mt-2 flex items-center gap-1 text-xs font-bold ${trend.value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              <span>{trend.value >= 0 ? '↑' : '↓'}</span>
              <span>{Math.abs(trend.value)}% {trend.label}</span>
            </div>
          )}
        </div>
        <div
          className="p-2.5 rounded-xl shrink-0"
          style={{
            background: `${color}22`,
            color,
            boxShadow: `0 0 12px ${color}30`,
            border: `1px solid ${color}30`,
          }}
        >
          {icon}
        </div>
      </div>
    </motion.div>
  );
}
