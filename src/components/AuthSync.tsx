import { useEffect, useRef } from 'react';
import { useAuth } from '../lib/auth';
import { useCollectionStore } from '../store/collectionStore';

/**
 * Invisible component that syncs the collection store with Supabase
 * whenever the auth state changes (login / logout).
 *
 * On first login: uploads existing localStorage data to Supabase,
 * then pulls the merged result back.
 * On subsequent logins: pulls from Supabase (server is source of truth).
 */
export function AuthSync() {
  const { user } = useAuth();
  const lastSyncedId = useRef<string | null>(null);

  useEffect(() => {
    if (!user) {
      lastSyncedId.current = null;
      return;
    }

    // Don't re-sync if we already synced for this user in this render cycle
    if (lastSyncedId.current === user.id) return;
    lastSyncedId.current = user.id;

    const store = useCollectionStore.getState();

    (async () => {
      // First time this user logs in on this device:
      // upload any localStorage data, then pull merged result
      if (store._syncUserId !== user.id && store.getUniqueCards() > 0) {
        console.log('[auth-sync] First sync — uploading local collection to Supabase');
        await store.uploadToSupabase(user.id);
      }

      // Always pull from Supabase — cloud is source of truth
      console.log('[auth-sync] Pulling collection from Supabase');
      await store.syncFromSupabase(user.id);
    })();
  }, [user]);

  return null;
}
