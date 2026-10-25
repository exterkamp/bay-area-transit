import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import type { Place, PlanResponse, PlanTrip } from '../../api/models';
import { apiUrls, withoutParam } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { delayInfo } from '../../lib/delay';
import { tripLabel } from '../../lib/agencies';
import { fareLabel, stationName, stopsText } from '../../lib/format';
import { PlaceRef, addRecent, legacyPairIds, placeRef, readPair, readRecents, swapPair } from '../../lib/places';
import { STORAGE_KEYS, readJson, writeJson } from '../../lib/storage';
import { countdown, formatDuration, formatInstant, nowInZone } from '../../lib/time';
import { PlacePicker } from '../../shared/place-picker';
import { RouteBadge } from '../../shared/route-badge';
import { StateView } from '../../shared/state';
import { StationNamePipe } from '../../shared/station-name.pipe';
import { StopTimeView } from '../../shared/stop-time';

const PAGE = 10;
const MAX_LIMIT = 50;

@Component({
  selector: 'app-planner-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PlacePicker, RouteBadge, StateView, StopTimeView, StationNamePipe],
  templateUrl: './planner-page.html',
  styleUrl: './planner-page.scss',
})
export class PlannerPage {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);
  private readonly http = inject(HttpClient);

  /** Optional ?from=&to= place ids (e.g. "Plan from here" on a board) override the remembered pair. */
  readonly from = input<string>();
  readonly to = input<string>();

  protected readonly fromPlace = signal<PlaceRef | null>(null);
  protected readonly toPlace = signal<PlaceRef | null>(null);
  private readonly fromId = computed(() => this.fromPlace()?.id ?? '');
  private readonly toId = computed(() => this.toPlace()?.id ?? '');
  protected readonly recents = signal<PlaceRef[]>([]);
  /** The operator whose remembered pair has been restored (restoring may need a fetch). */
  protected readonly restored = signal('');
  protected readonly mode = signal<'now' | 'at'>('now');
  protected readonly at = signal('');
  protected readonly limit = signal(PAGE);

  private restoredFor = '';

  protected readonly sameStation = computed(() => !!this.fromId() && this.fromId() === this.toId());

  private readonly planUrl = computed(() => {
    const from = this.fromId();
    const to = this.toId();
    if (!from || !to || from === to || this.op.noFeed()) return undefined;
    const at = this.mode() === 'at' && this.at() ? this.at() : null;
    return apiUrls.plan(this.op.code(), { from, to, at, limit: this.limit() });
  });

  protected readonly plan = polled<PlanResponse>(() => this.planUrl(), {
    intervalMs: 60_000,
    enabled: () => this.mode() === 'now',
    what: 'that trip',
    keepPreviousWhile: (a, b) => withoutParam(a, 'limit') === withoutParam(b, 'limit'),
  });

  protected readonly fare = computed(() => fareLabel(this.plan.data()?.fare));
  protected readonly updated = computed(() => {
    const t = this.plan.updatedAt();
    return t ? formatInstant(t, this.op.timeZone()) : '';
  });
  protected readonly canShowMore = computed(() => {
    const p = this.plan.data();
    return !!p && p.trips.length >= this.limit() && this.limit() < MAX_LIMIT;
  });

  constructor() {
    // Restore the pair once per operator, once /operators says it has a feed.
    effect(() => {
      const code = this.op.code();
      if (!this.op.feed() || this.restoredFor === code) return;
      this.restoredFor = code;
      untracked(() => void this.restore(code));
    });

    // Remember the pair as it changes.
    effect(() => {
      const pair = { from: this.fromPlace(), to: this.toPlace() };
      const code = this.op.code();
      if (this.restored() !== code) return;
      writeJson(STORAGE_KEYS.trip(code), pair);
    });
  }

  private async restore(code: string): Promise<void> {
    this.recents.set(readRecents(readJson(STORAGE_KEYS.recents(code), null)));
    const remembered = readPair(readJson(STORAGE_KEYS.trip(code), null));
    let from: PlaceRef | string | null = remembered.from;
    let to: PlaceRef | string | null = remembered.to;
    if (!from && !to && code === 'RG') {
      // First visit since the app went regional: carry over the Caltrain trip.
      const legacy = legacyPairIds(readJson(STORAGE_KEYS.legacyTrip, null));
      from = legacy?.from || null;
      to = legacy?.to || null;
    }
    const fromQuery = untracked(this.from);
    const toQuery = untracked(this.to);
    const idOf = (v: PlaceRef | string | null) => (typeof v === 'string' ? v : (v?.id ?? ''));
    if (fromQuery && idOf(from) !== fromQuery) {
      // "Plan from here" at the place you last went *to*: flip the remembered trip.
      if (!toQuery && idOf(to) === fromQuery) to = from;
      from = fromQuery;
    }
    if (toQuery && idOf(to) !== toQuery) to = toQuery;

    const [f, t] = await Promise.all([this.resolve(code, from), this.resolve(code, to)]);
    if (this.op.code() !== code) return;
    this.fromPlace.set(f);
    this.toPlace.set(t && t.id !== f?.id ? t : null);
    this.restored.set(code);
  }

  /** A remembered ref as is; a bare id (from a link or the old app) looked up. */
  private async resolve(code: string, v: PlaceRef | string | null): Promise<PlaceRef | null> {
    if (!v) return null;
    if (typeof v !== 'string') return v;
    try {
      return placeRef(await firstValueFrom(this.http.get<Place>(apiUrls.place(code, v))));
    } catch {
      return null;
    }
  }

  private remember(p: PlaceRef): void {
    const list = addRecent(this.recents(), p);
    this.recents.set(list);
    writeJson(STORAGE_KEYS.recents(this.op.code()), list);
  }

  protected setFrom(p: PlaceRef): void {
    this.fromPlace.set(p);
    this.remember(p);
    this.limit.set(PAGE);
  }

  protected setTo(p: PlaceRef): void {
    this.toPlace.set(p);
    this.remember(p);
    this.limit.set(PAGE);
  }

  protected swap(): void {
    const s = swapPair({ from: this.fromPlace(), to: this.toPlace() });
    this.fromPlace.set(s.from);
    this.toPlace.set(s.to);
    this.limit.set(PAGE);
  }

  protected setMode(mode: 'now' | 'at'): void {
    if (mode === 'at' && !this.at()) this.at.set(nowInZone(this.op.timeZone()));
    this.mode.set(mode);
    this.limit.set(PAGE);
  }

  protected setAt(value: string): void {
    this.at.set(value);
    this.limit.set(PAGE);
  }

  protected more(): void {
    this.limit.update((n) => Math.min(MAX_LIMIT, n + PAGE));
  }

  protected countdownFor(t: PlanTrip): string {
    if (t.status === 'canceled' || this.mode() !== 'now') return '';
    return countdown(delayInfo(t.depart).effective, this.clock.now());
  }

  protected noTripsTitle(p: PlanResponse): string {
    return p.served ? 'Nothing in the next day' : 'No direct trips';
  }

  /** Empty: either the trip runs on other days, or it needs a transfer the planner can't plan. */
  protected noDirectMessage(p: PlanResponse): string {
    const from = stationName(p.from.name);
    const to = stationName(p.to.name);
    if (p.served) {
      return `Trips from ${from} to ${to} run on other days. Pick "Depart at" and a later date to see them.`;
    }
    return (
      `Nothing runs straight from ${from} to ${to}. ` +
      "This journey needs a transfer, and the planner doesn't plan those yet. The departure boards at each end show what leaves from where."
    );
  }

  protected readonly duration = formatDuration;
  protected readonly tripLabel = tripLabel;
  protected readonly stopsText = stopsText;
}
