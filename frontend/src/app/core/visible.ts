import { EMPTY, Observable, filter, fromEvent, interval, map, merge } from 'rxjs';

/**
 * Ticks every `ms` while the tab is visible, and once on coming back if a
 * tick was missed while it was hidden. Nothing outside a browser.
 */
export function whileVisible(ms: number): Observable<void> {
  if (typeof document === 'undefined') return EMPTY;
  let lastTick = Date.now();
  return merge(
    interval(ms).pipe(filter(() => !document.hidden)),
    fromEvent(document, 'visibilitychange').pipe(filter(() => !document.hidden && Date.now() - lastTick >= ms)),
  ).pipe(
    map(() => {
      lastTick = Date.now();
    }),
  );
}
