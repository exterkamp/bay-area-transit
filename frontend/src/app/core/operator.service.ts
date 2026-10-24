import { Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';
import type { Operator, Station } from '../api/models';
import { apiUrls } from '../api/urls';
import { normalizeOperator } from '../lib/format';
import { summarizeRealtime } from '../lib/staleness';
import { ClockService } from './clock.service';
import { polled } from './polled';

export const DEFAULT_OPERATOR = 'CT';
const FALLBACK_TZ = 'America/Los_Angeles';

/**
 * The operator the app is looking at, and everything app-wide about it.
 *
 * The UI is Caltrain-first, but every request goes through `code()` so BART
 * can slot in. `?op=BA` on any URL switches; the choice sticks for the rest
 * of the session even on links that don't carry it.
 */
@Injectable({ providedIn: 'root' })
export class OperatorService {
  private readonly clock = inject(ClockService);
  private readonly router = inject(Router);

  readonly code = signal(DEFAULT_OPERATOR);

  /** Refreshed every 30 s so "Updated …" moves soon after each realtime poll. */
  readonly operators = polled<Operator[]>(() => apiUrls.operators(), { intervalMs: 30_000 });

  readonly operator = computed(() => this.operators.data()?.find((o) => o.code === this.code()));

  /** True once /operators has answered and doesn't list this code. */
  readonly unknownOperator = computed(() => {
    const list = this.operators.data();
    return !!list && !list.some((o) => o.code === this.code());
  });

  /** True once we know there's no imported feed for this operator. */
  readonly noFeed = computed(() => this.operator()?.feed === null);

  readonly name = computed(() => this.operator()?.name ?? (this.code() === 'CT' ? 'Caltrain' : this.code()));
  readonly timeZone = computed(() => this.operator()?.timezone ?? FALLBACK_TZ);
  readonly feed = computed(() => this.operator()?.feed ?? null);

  readonly realtime = computed(() => summarizeRealtime(this.operator()?.realtime, this.clock.now()));

  /** Shared by the planner, boards, trip detail and map; the list rarely changes. */
  readonly stations = polled<Station[]>(() => apiUrls.stations(this.code()), { what: 'stations' });

  constructor() {
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe((e) => {
        const op = this.router.parseUrl(e.urlAfterRedirects).queryParamMap.get('op');
        if (op) this.code.set(normalizeOperator(op, DEFAULT_OPERATOR));
      });
  }
}
