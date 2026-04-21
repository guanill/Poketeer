// Canonical era labels + chronological order shared across Sets page and SetCard.

// Chronological order (oldest → newest). The Sets page reverses this for
// the default date-desc sort. Labels here must match what getEra returns.
export const ERA_ORDER: string[] = [
  'Base',
  'Gym',
  'Neo',
  'VS',
  'Web',
  'E-Card',
  'EX',
  'Diamond & Pearl',
  'Platinum',
  'HeartGold & SoulSilver',
  'Black & White',
  'XY',
  'Sun & Moon',
  'Sword & Shield',
  'Scarlet & Violet',
  'Mega Evolution',
];

export function getEra(series: string | undefined | null): string {
  if (!series) return 'Other';
  const s = series.trim();

  // Japanese series strings → canonical EN era names
  if (s === 'ポケモンカードゲーム スカーレット&バイオレット') return 'Scarlet & Violet';
  if (s === 'サン＆ムーン' || s === 'サン&ムーン') return 'Sun & Moon';
  if (s === '剣と盾') return 'Sword & Shield';
  if (s === 'Pocket Monsters Card Game') return 'Base';
  if (s === 'e-Card') return 'E-Card';
  if (s === 'ADV' || s === 'PCG') return 'EX';       // JP equivalents of the EN EX era
  if (s === 'LEGEND') return 'HeartGold & SoulSilver';
  if (s === 'XY BREAK') return 'XY';

  return s; // EN labels already canonical
}
