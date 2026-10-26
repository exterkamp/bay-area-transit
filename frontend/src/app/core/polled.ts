import { httpResource } from '@angular/common/http';
import { Signal, computed, linkedSignal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiErrorView, classifyError } from '../lib/api-error';
import { whileVisible } from './visible';

export interface Polled<T> {
  /** The latest good response for the current URL; kept through refresh failures. */
  data: Signal<T | undefined>;
  /** The current failure, if the most recent request failed. */
  error: Signal<ApiErrorView | null>;
  /** In flight with nothing to show yet: render a loading state. */
  loading: Signal<boolean>;
  /** In flight while showing earlier data. */
  refreshing: Signal<boolean>;
  /** Epoch ms of the last good response. */
  updatedAt: Signal<number | null>;
  reload(): void;
}

export interface PolledOptions {
  /** Re-fetch this often. Paused while the tab is hidden; caught up when it returns. */
  intervalMs?: number;
  /** Polling only runs while this is true (default always). */
  enabled?: () => boolean;
  /** What the request is for, for error text ("that station"). */
  what?: string;
  /**
   * When the URL changes, keep showing the previous data while the new one
   * loads if this returns true (e.g. only `limit` changed).
   */
  keepPreviousWhile?: (previousUrl: string, nextUrl: string) => boolean;
}

interface Good<T> {
  url: string;
  value: T;
  at: number;
}

/**
 * An httpResource that a page can poll without flicker: it remembers the last
 * good value so a failed refresh shows an inline warning over stale data
 * instead of wiping the screen. Call in an injection context.
 */
export function polled<T>(url: () => string | undefined, opts: PolledOptions = {}): Polled<T> {
  const ref = httpResource<T>(() => url());

  // Each response replaces the last good one; loading and errors keep it.
  const last = linkedSignal<T | undefined, Good<T> | null>({
    source: () => (ref.hasValue() ? (ref.value() as T) : undefined),
    computation: (value, previous) => {
      const u = untracked(url);
      return value !== undefined && u ? { url: u, value, at: Date.now() } : (previous?.value ?? null);
    },
  });

  // The last good response, if it's for this URL (or one close enough to show meanwhile).
  const kept = computed(() => {
    const l = last();
    const cur = url();
    return l && cur && (l.url === cur || opts.keepPreviousWhile?.(l.url, cur)) ? l : null;
  });

  const data = computed<T | undefined>(() => (ref.hasValue() ? (ref.value() as T) : kept()?.value));
  const inFlight = ref.isLoading;

  const reload = () => {
    if (untracked(url)) ref.reload();
  };

  if (opts.intervalMs) {
    const enabled = opts.enabled ?? (() => true);
    whileVisible(opts.intervalMs)
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (untracked(enabled)) reload();
      });
  }

  return {
    data,
    error: computed(() => (ref.status() === 'error' ? classifyError(ref.error(), opts.what) : null)),
    loading: computed(() => inFlight() && data() === undefined),
    refreshing: computed(() => inFlight() && data() !== undefined),
    updatedAt: computed(() => kept()?.at ?? null),
    reload,
  };
}
