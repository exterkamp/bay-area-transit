import { DestroyRef, Injectable, inject, signal } from '@angular/core';

/** A coarse "now" for countdowns and staleness, ticking every 15 s. */
@Injectable({ providedIn: 'root' })
export class ClockService {
  private readonly _now = signal(Date.now());
  readonly now = this._now.asReadonly();

  constructor() {
    const id = setInterval(() => this._now.set(Date.now()), 15_000);
    const onVisible = () => {
      if (!document.hidden) this._now.set(Date.now());
    };
    document.addEventListener('visibilitychange', onVisible);
    inject(DestroyRef).onDestroy(() => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    });
  }
}
