/** Returns true when running inside a Capacitor native container (Android/iOS). */
export const isNativePlatform = (): boolean =>
  !!(window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } })
    .Capacitor?.isNativePlatform?.();
