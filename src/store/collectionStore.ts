import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { OwnedCard, WishlistItem, CardCondition, CardVariant } from '../types';
import { supabase } from '../lib/supabase';

interface CollectionStore {
  owned: Record<string, OwnedCard>;
  wishlist: WishlistItem[];
  customPrices: Record<string, number>;
  /** The user ID currently synced to Supabase (null = offline / localStorage only) */
  _syncUserId: string | null;

  // Collection actions
  addCard: (cardId: string, pricePaid?: number, condition?: CardCondition, notes?: string) => void;
  removeCard: (cardId: string) => void;
  updateCard: (cardId: string, updates: Partial<OwnedCard>) => void;
  toggleVariant: (cardId: string, variant: CardVariant) => void;
  isOwned: (cardId: string) => boolean;
  getOwnedCount: (setId: string, cardIds: string[]) => number;

  // Wishlist actions
  addToWishlist: (cardId: string, targetPrice?: number, priority?: WishlistItem['priority']) => void;
  removeFromWishlist: (cardId: string) => void;
  isInWishlist: (cardId: string) => boolean;
  updateWishlistItem: (cardId: string, updates: Partial<WishlistItem>) => void;

  // Price actions
  setCustomPrice: (cardId: string, price: number) => void;
  removeCustomPrice: (cardId: string) => void;

  // Stats
  getTotalValue: (getMarketPrice: (cardId: string) => number | null) => number;
  getTotalSpent: () => number;
  getTotalCards: () => number;
  getUniqueCards: () => number;

  // Sync
  syncFromSupabase: (userId: string) => Promise<void>;
  uploadToSupabase: (userId: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Supabase sync helpers (fire-and-forget, best-effort)
// ---------------------------------------------------------------------------

async function _getUser(): Promise<string | null> {
  const { data } = await supabase.auth.getUser();
  return data.user?.id ?? null;
}

async function _upsertCollection(userId: string, cardId: string, card: OwnedCard) {
  await supabase.from('collections').upsert({
    user_id: userId,
    card_id: cardId,
    quantity: card.quantity,
    price_paid: card.pricePaid ?? null,
    condition: card.condition,
    notes: card.notes ?? null,
    date_added: card.dateAdded,
    variants: card.variants ?? [],
  });
}

async function _deleteCollection(userId: string, cardId: string) {
  await supabase.from('collections').delete().eq('user_id', userId).eq('card_id', cardId);
}

async function _upsertWishlist(userId: string, item: WishlistItem) {
  await supabase.from('wishlist').upsert({
    user_id: userId,
    card_id: item.cardId,
    target_price: item.targetPrice ?? null,
    priority: item.priority,
    date_added: item.dateAdded,
  });
}

async function _deleteWishlist(userId: string, cardId: string) {
  await supabase.from('wishlist').delete().eq('user_id', userId).eq('card_id', cardId);
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useCollectionStore = create<CollectionStore>()(
  persist(
    (set, get) => ({
      owned: {},
      wishlist: [],
      customPrices: {},
      _syncUserId: null,

      addCard: (cardId, pricePaid, condition = 'Near Mint', notes) => {
        set(state => {
          const existing = state.owned[cardId];
          const card: OwnedCard = existing
            ? { ...existing, quantity: existing.quantity + 1 }
            : { cardId, quantity: 1, pricePaid, condition, notes, dateAdded: new Date().toISOString() };
          // Sync to Supabase in background
          _getUser().then(uid => { if (uid) _upsertCollection(uid, cardId, card); });
          return { owned: { ...state.owned, [cardId]: card } };
        });
      },

      removeCard: (cardId) => {
        set(state => {
          const next = { ...state.owned };
          delete next[cardId];
          _getUser().then(uid => { if (uid) _deleteCollection(uid, cardId); });
          return { owned: next };
        });
      },

      updateCard: (cardId, updates) => {
        set(state => {
          const card = { ...state.owned[cardId], ...updates };
          _getUser().then(uid => { if (uid) _upsertCollection(uid, cardId, card); });
          return { owned: { ...state.owned, [cardId]: card } };
        });
      },

      toggleVariant: (cardId, variant) => {
        set(state => {
          const existing = state.owned[cardId];
          if (!existing) return state;
          const current = existing.variants ?? [];
          const has = current.includes(variant);
          const variants = has ? current.filter(v => v !== variant) : [...current, variant];
          const card = { ...existing, variants };
          _getUser().then(uid => { if (uid) _upsertCollection(uid, cardId, card); });
          return { owned: { ...state.owned, [cardId]: card } };
        });
      },

      isOwned: (cardId) => !!get().owned[cardId],

      getOwnedCount: (_, cardIds) => {
        const owned = get().owned;
        return cardIds.filter(id => !!owned[id]).length;
      },

      addToWishlist: (cardId, targetPrice, priority = 'Medium') => {
        if (get().isInWishlist(cardId)) return;
        const item: WishlistItem = { cardId, targetPrice, priority, dateAdded: new Date().toISOString() };
        _getUser().then(uid => { if (uid) _upsertWishlist(uid, item); });
        set(state => ({ wishlist: [...state.wishlist, item] }));
      },

      removeFromWishlist: (cardId) => {
        _getUser().then(uid => { if (uid) _deleteWishlist(uid, cardId); });
        set(state => ({ wishlist: state.wishlist.filter(w => w.cardId !== cardId) }));
      },

      isInWishlist: (cardId) => get().wishlist.some(w => w.cardId === cardId),

      updateWishlistItem: (cardId, updates) => {
        set(state => {
          const wishlist = state.wishlist.map(w => w.cardId === cardId ? { ...w, ...updates } : w);
          const updated = wishlist.find(w => w.cardId === cardId);
          if (updated) _getUser().then(uid => { if (uid) _upsertWishlist(uid, updated); });
          return { wishlist };
        });
      },

      setCustomPrice: (cardId, price) => {
        set(state => ({ customPrices: { ...state.customPrices, [cardId]: price } }));
      },

      removeCustomPrice: (cardId) => {
        set(state => {
          const next = { ...state.customPrices };
          delete next[cardId];
          return { customPrices: next };
        });
      },

      getTotalValue: (getMarketPrice) => {
        const { owned } = get();
        return Object.entries(owned).reduce((sum, [cardId, card]) => {
          const price = getMarketPrice(cardId) ?? 0;
          return sum + price * card.quantity;
        }, 0);
      },

      getTotalSpent: () => {
        const { owned } = get();
        return Object.values(owned).reduce((sum, card) => sum + (card.pricePaid ?? 0) * card.quantity, 0);
      },

      getTotalCards: () => Object.values(get().owned).reduce((sum, c) => sum + c.quantity, 0),

      getUniqueCards: () => Object.keys(get().owned).length,

      // Pull collection + wishlist from Supabase into local state
      syncFromSupabase: async (userId: string) => {
        const [colRes, wlRes] = await Promise.all([
          supabase.from('collections').select('*').eq('user_id', userId),
          supabase.from('wishlist').select('*').eq('user_id', userId),
        ]);

        const owned: Record<string, OwnedCard> = {};
        for (const row of colRes.data ?? []) {
          owned[row.card_id] = {
            cardId: row.card_id,
            quantity: row.quantity,
            pricePaid: row.price_paid ?? undefined,
            condition: row.condition as CardCondition,
            notes: row.notes ?? undefined,
            dateAdded: row.date_added,
            variants: (row as Record<string, unknown>).variants as CardVariant[] ?? [],
          };
        }

        const wishlist: WishlistItem[] = (wlRes.data ?? []).map(row => ({
          cardId: row.card_id,
          targetPrice: row.target_price ?? undefined,
          priority: row.priority as WishlistItem['priority'],
          dateAdded: row.date_added,
        }));

        set({ owned, wishlist, _syncUserId: userId });
      },

      // Push current local state to Supabase (useful for first-time migration)
      uploadToSupabase: async (userId: string) => {
        const { owned, wishlist } = get();

        const colRows = Object.entries(owned).map(([cardId, card]) => ({
          user_id: userId,
          card_id: cardId,
          quantity: card.quantity,
          price_paid: card.pricePaid ?? null,
          condition: card.condition,
          notes: card.notes ?? null,
          date_added: card.dateAdded,
          variants: card.variants ?? [],
        }));

        const wlRows = wishlist.map(item => ({
          user_id: userId,
          card_id: item.cardId,
          target_price: item.targetPrice ?? null,
          priority: item.priority,
          date_added: item.dateAdded,
        }));

        if (colRows.length > 0) {
          await supabase.from('collections').upsert(colRows);
        }
        if (wlRows.length > 0) {
          await supabase.from('wishlist').upsert(wlRows);
        }

        set({ _syncUserId: userId });
      },
    }),
    { name: 'poketeer-collection' },
  ),
);
