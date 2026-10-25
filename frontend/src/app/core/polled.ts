import { httpResource } from '@angular/common/http';
import { DestroyRef, Signal, computed, effect, inject, signal, untracked } from '@angular/core';
import { ApiErrorView, classifyError } from '../lib/api-error';

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

/**
 * An httpResource that a page can poll without flicker: it remembers the last
 * good value so a failed refresh shows an inline warning over stale data
 * instead of wiping the screen. Call in an injection context.
 */
export function polled<T>(url: () => string | undefined, opts: PolledOptions = {}): Polled<T> {
  const ref = httpResource<T>(() => url());
  const last = signal<{ url: string; value: T; at: number } | null>(null);

  effect(() => {
    if (ref.hasValue()) {
      const value = ref.value() as T;
      const u = untracked(url);
      if (u) last.set({ url: u, value, at: Date.now() });
    }
  });

  const keep = (prev: string, cur: string | undefined) =>
    !!cur && (prev === cur || !!opts.keepPreviousWhile?.(prev, cur));

  const data = computed<T | undefined>(() => {
    if (ref.hasValue()) return ref.value() as T;
    const l = last();
    return l && keep(l.url, url()) ? l.value : undefined;
  });

  const error = computed<ApiErrorView | null>(() =>
    ref.status() === 'error' ? classifyError(ref.error(), opts.what) : null,
  );

  const inFlight = computed(() => ref.isLoading());

  const reload = () => {
    if (untracked(url)) ref.reload();
  };

  if (opts.intervalMs && typeof window !== 'undefined') {
    const enabled = opts.enabled ?? (() => true);
    let lastTick = Date.now();
    const tick = () => {
      if (document.hidden || !untracked(enabled)) return;
      lastTick = Date.now();
      reload();
    };
    const id = setInterval(tick, opts.intervalMs);
    const onVisible = () => {
      if (!document.hidden && Date.now() - lastTick >= opts.intervalMs!) tick();
    };
    document.addEventListener('visibilitychange', onVisible);
    inject(DestroyRef).onDestroy(() => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    });
  }

  return {
    data,
    error,
    loading: computed(() => inFlight() && data() === undefined),
    refreshing: computed(() => inFlight() && data() !== undefined),
    updatedAt: computed(() => {
      const l = last();
      return l && keep(l.url, url()) ? l.at : null;
    }),
    reload,
  };
}
