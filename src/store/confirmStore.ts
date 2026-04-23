import { create } from 'zustand';

type Tone = 'danger' | 'neutral';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  tone?: Tone;
}

interface ConfirmState {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
  tone: Tone;
  _resolve: ((value: boolean) => void) | null;

  confirm: (opts: ConfirmOptions) => Promise<boolean>;
  handleConfirm: () => void;
  handleCancel: () => void;
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  isOpen: false,
  title: '',
  message: '',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  tone: 'danger',
  _resolve: null,

  confirm: (opts) =>
    new Promise<boolean>(resolve => {
      set({
        isOpen: true,
        title: opts.title,
        message: opts.message,
        confirmText: opts.confirmText ?? 'Confirm',
        cancelText: opts.cancelText ?? 'Cancel',
        tone: opts.tone ?? 'danger',
        _resolve: resolve,
      });
    }),

  handleConfirm: () => {
    const { _resolve } = get();
    _resolve?.(true);
    set({ isOpen: false, _resolve: null });
  },

  handleCancel: () => {
    const { _resolve } = get();
    _resolve?.(false);
    set({ isOpen: false, _resolve: null });
  },
}));

/** Convenience wrapper so callers don't need to grab the hook inline. */
export const confirmAction = (opts: ConfirmOptions): Promise<boolean> =>
  useConfirmStore.getState().confirm(opts);
