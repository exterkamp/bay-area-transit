import { Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';
import type { Agency, AgencyId, Operator } from '../api/models';
import { apiUrls } from '../api/urls';
import { agencyName, compareAgencies } from '../lib/agencies';
import { normalizeOperator } from '../lib/format';
import { summarizeRealtime } from '../lib/staleness';
import { ClockService } from './clock.service';
import { polled } from './polled';

export const DEFAULT_OPERATOR = 'RG';
const FALLBACK_TZ = 'America/Los_Angeles';

/**
 * The operator the app is looking at, and everything app-wide about it.
 *
 * By default that's RG, 511's regional feed (Muni rail, BART, SamTrans and
 * Caltrain in one). `?op=CT` on any URL switches to a single agency's own
 * feed; the choice sticks for the rest of the session even on links that
 * don't carry it.
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

  /** The agencies in this operator's feed, as listed by /operators. */
  readonly agencyIds = computed<AgencyId[]>(() => [...(this.operator()?.agencies ?? [])].sort(compareAgencies));
  readonly multiAgency = computed(() => this.agencyIds().length > 1);

  /** What to call this source: "Caltrain" for one agency, the agencies for a regional feed. */
  readonly name = computed(() => {
    const ids = this.agencyIds();
    if (ids.length === 1) return agencyName(ids[0]!, this.operator()?.name);
    if (ids.length > 1) return ids.map((id) => agencyName(id)).join(' · ');
    return this.operator()?.name ?? this.code();
  });
  readonly timeZone = computed(() => this.operator()?.timezone ?? FALLBACK_TZ);
  readonly feed = computed(() => this.operator()?.feed ?? null);

  readonly realtime = computed(() => summarizeRealtime(this.operator()?.realtime, this.clock.now()));

  /** Names and route types for every agency in the feed; fetched once per operator. */
  readonly agencies = polled<Agency[]>(() => (this.noFeed() ? undefined : apiUrls.agencies(this.code())));

  /** "Muni", or the feed's own name for an agency we have no short name for. */
  agencyName(id: AgencyId): string {
    return agencyName(id, this.agencies.data()?.find((a) => a.id === id)?.name);
  }

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
