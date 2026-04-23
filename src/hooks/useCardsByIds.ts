import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { pokemonTCGService } from '../services/pokemonTCG';

// Sort IDs before keying so `[a, b, c]` and `[c, b, a]` share the same cache
// entry, and adding/removing a card only invalidates the key when the *set*
// of IDs actually changes.
function useSortedIds(cardIds: string[]): string[] {
  const key = cardIds.slice().sort().join(',');
  return useMemo(() => (key ? key.split(',') : []), [key]);
}

export function useCardsByIds(cardIds: string[]) {
  const ids = useSortedIds(cardIds);
  return useQuery({
    queryKey: ['cards-by-ids', ids.join(',')],
    queryFn: () => pokemonTCGService.getCardsByIds(ids),
    enabled: ids.length > 0,
    staleTime: 1000 * 60 * 10,
  });
}

export function usePricesByIds(cardIds: string[]) {
  const ids = useSortedIds(cardIds);
  return useQuery({
    queryKey: ['prices-by-ids', ids.join(',')],
    queryFn: () => pokemonTCGService.getPrices(ids),
    enabled: ids.length > 0,
    staleTime: 1000 * 60 * 60,
  });
}
