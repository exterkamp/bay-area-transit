import { Service } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { EMPTY, Observable, filter, fromEvent, interval, map, merge } from 'rxjs';

/** Every 15 s, and on coming back to the tab. */
function ticks(): Observable<unknown> {
  if (typeof document === 'undefined') return EMPTY;
  return merge(interval(15_000), fromEvent(document, 'visibilitychange').pipe(filter(() => !document.hidden)));
}

/** A coarse "now" for countdowns and staleness. */
@Service()
export class ClockService {
  readonly now = toSignal(ticks().pipe(map(() => Date.now())), { initialValue: Date.now() });
}
