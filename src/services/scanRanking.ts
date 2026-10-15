import type { ScanMatch } from './cardScanService';

export interface NumberMatchEvidence {
  cardNumber: string;
  setHint: string;
  nameHints: string[];
  hpHint: string;
  supertypeHint: string;
  nearbyNumbers: string[];
}

function normalizeNumber(value: string): string {
  const normalized = value.replace(/\s+/g, '').toUpperCase();
  return /^\d+$/.test(normalized) ? normalized.replace(/^0+(?=\d)/, '') : normalized;
}

function normalizeName(value: string): string {
  return value.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
}

function nameSimilarity(left: string, right: string): number {
  const a = normalizeName(left);
  const b = normalizeName(right);
  if (a === b) return 1;
  if (!a || !b) return 0;
  if (a.includes(b) || b.includes(a)) return Math.min(a.length, b.length) / Math.max(a.length, b.length);

  let previous = Array.from({ length: b.length + 1 }, (_, index) => index);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    previous = current;
  }
  return 1 - previous[b.length] / Math.max(a.length, b.length);
}

/** Rank number-search results using distinct OCR signals and penalize conflicts. */
export function rankNumberMatches(
  candidates: ScanMatch[],
  evidence: NumberMatchEvidence,
): ScanMatch[] {
  const normalizedNumber = normalizeNumber(evidence.cardNumber);
  const normalizedSet = normalizeName(evidence.setHint);
  const nearbyNumbers = new Set(evidence.nearbyNumbers.map(normalizeNumber));

  return candidates.map(candidate => {
    const exactNumber = normalizeNumber(candidate.number) === normalizedNumber;
    const nearbyNumber = nearbyNumbers.has(normalizeNumber(candidate.number));
    const candidateSet = normalizeName(candidate.set_id.replace(/-(?:en|ja|th)$/i, ''));
    const setMatches = !!normalizedSet &&
      (candidateSet === normalizedSet || candidateSet.startsWith(normalizedSet) || normalizedSet.startsWith(candidateSet));
    const nameScore = evidence.nameHints.length > 0
      ? Math.max(...evidence.nameHints.flatMap(hint => [
          nameSimilarity(hint, candidate.name),
          candidate.name_en ? nameSimilarity(hint, candidate.name_en) : 0,
        ]))
      : 0;
    const hasName = evidence.nameHints.length > 0;
    const hasSet = !!normalizedSet;
    let confidence = (exactNumber ? 0.35 : nearbyNumber ? 0.15 : 0) +
      nameScore * 0.5 + (setMatches ? 0.15 : 0);

    if (hasSet && !setMatches) confidence -= 0.06;
    if (hasName && nameScore < 0.35) confidence -= 0.3;
    if (evidence.cardNumber && !exactNumber && !nearbyNumber && hasName) confidence -= 0.05;
    if (evidence.hpHint) {
      confidence += candidate.hp === evidence.hpHint ? 0.05 : -0.06;
    }
    if (evidence.supertypeHint) {
      confidence += candidate.supertype === evidence.supertypeHint ? 0.03 : -0.03;
    }

    return { ...candidate, confidence: Math.max(0, Math.min(0.99, confidence)) };
  }).sort((a, b) => b.confidence - a.confidence);
}

/** Combine OCR and visual candidates without comparing their unrelated raw scores. */
export function mergeScanMatches(
  ocrMatches: ScanMatch[],
  visualMatches: ScanMatch[],
  topK: number,
): ScanMatch[] {
  const bestById = (matches: ScanMatch[]) => {
    const best = new Map<string, ScanMatch>();
    for (const match of matches) {
      if (!best.has(match.id) || best.get(match.id)!.confidence < match.confidence) {
        best.set(match.id, match);
      }
    }
    return best;
  };
  const ocrById = bestById(ocrMatches);
  const visualById = bestById(visualMatches);
  const ids = new Set([...ocrById.keys(), ...visualById.keys()]);
  const merged: ScanMatch[] = [];

  for (const id of ids) {
    const ocr = ocrById.get(id);
    const visual = visualById.get(id);
    const match = ocr ?? visual;
    if (!match) continue;

    const ocrConfidence = ocr?.confidence ?? 0;
    const visualConfidence = visual?.confidence ?? 0;
    const confidence = ocr
      ? ocrConfidence * 0.7 + visualConfidence * 0.3 +
        (visual ? Math.min(ocrConfidence, visualConfidence) * 0.1 : 0)
      : visualConfidence * 0.3;

    merged.push({
      ...match,
      confidence: Math.min(0.99, confidence),
      method: ocr && visual ? 'ocr+visual' : ocr ? 'ocr' : 'visual',
    });
  }

  return merged.sort((a, b) => b.confidence - a.confidence).slice(0, topK);
}
