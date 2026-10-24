// localStorage that never throws. Framework-free.
//
// Storage can be missing (SSR, tests), blocked (privacy settings), full, or
// hold junk from an older build. Every read falls back, every write is
// best-effort.

export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function defaultStore(): KeyValueStore | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function readJson<T>(key: string, fallback: T, store: KeyValueStore | null = defaultStore()): T {
  if (!store) return fallback;
  try {
    const raw = store.getItem(key);
    if (raw == null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown, store: KeyValueStore | null = defaultStore()): void {
  if (!store) return;
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    // Full or blocked: remembering is a nicety.
  }
}

export const STORAGE_KEYS = {
  /** Last from/to for an operator. */
  trip: (op: string) => `bat.trip.${op}`,
  dismissedAlerts: 'bat.dismissedAlerts',
} as const;
