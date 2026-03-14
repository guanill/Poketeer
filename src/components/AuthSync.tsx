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
  const syncedRef = useRef<string | null>(null);
  const { _syncUserId, syncFromSupabase, uploadToSupabase, getUniqueCards } = useCollectionStore();

  useEffect(() => {
    if (!user) {
      syncedRef.current = null;
      return;
    }

    // Don't re-sync if we already synced for this user in this session
    if (syncedRef.current === user.id) return;
    syncedRef.current = user.id;

    (async () => {
      // First time this user logs in on this device:
      // upload any localStorage data, then pull merged result
      if (_syncUserId !== user.id && getUniqueCards() > 0) {
        console.log('[auth-sync] First sync — uploading local collection to Supabase');
        await uploadToSupabase(user.id);
      }
      console.log('[auth-sync] Pulling collection from Supabase');
      await syncFromSupabase(user.id);
    })();
  }, [user, _syncUserId, syncFromSupabase, uploadToSupabase, getUniqueCards]);

  return null;
}
