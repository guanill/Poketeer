export const RARITY_ORDER: Record<string, number> = {
  'common': 1, 'uncommon': 2, 'rare': 3, 'rare holo': 4,
  'rare holo ex': 5, 'rare holo gx': 5, 'rare holo v': 5, 'rare ultra': 6,
  'rare holo vmax': 6, 'rare holo vstar': 6, 'rare secret': 7, 'rare rainbow': 7,
  'rare shiny': 6, 'rare shiny gx': 7, 'rare ace': 5,
  'double rare': 5, 'ultra rare': 6, 'illustration rare': 7,
  'special illustration rare': 8, 'hyper rare': 9, 'shiny rare': 5,
  'shiny ultra rare': 7, 'ace spec rare': 5,
};

export function getRarityRank(rarity?: string): number {
  if (!rarity) return 0;
  return RARITY_ORDER[rarity.toLowerCase()] ?? 3;
}

export const TYPE_COLORS: Record<string, { color: string; bg: string }> = {
  Fire: { color: '#f97316', bg: 'rgba(249,115,22,0.15)' },
  Water: { color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  Grass: { color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  Lightning: { color: '#facc15', bg: 'rgba(250,204,21,0.15)' },
  Psychic: { color: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
  Fighting: { color: '#b45309', bg: 'rgba(180,83,9,0.15)' },
  Darkness: { color: '#6366f1', bg: 'rgba(99,102,241,0.15)' },
  Metal: { color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' },
  Fairy: { color: '#ec4899', bg: 'rgba(236,72,153,0.15)' },
  Dragon: { color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
  Colorless: { color: '#9ca3af', bg: 'rgba(156,163,175,0.15)' },
};
