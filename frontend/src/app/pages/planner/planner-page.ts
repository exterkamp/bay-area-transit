import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { PlanResponse, PlanTrip } from '../../api/models';
import { apiUrls, withoutParam } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { delayInfo } from '../../lib/delay';
import { fareLabel, stationName, stopsText } from '../../lib/format';
import { StationPair, sanitizePair, swapPair } from '../../lib/stations';
import { STORAGE_KEYS, readJson, writeJson } from '../../lib/storage';
import { countdown, formatDuration, formatInstant, nowInZone } from '../../lib/time';
import { RouteBadge } from '../../shared/route-badge';
import { StateView } from '../../shared/state';
import { StationNamePipe } from '../../shared/station-name.pipe';
import { StopTimeView } from '../../shared/stop-time';

const PAGE = 10;
const MAX_LIMIT = 50;

@Component({
  selector: 'app-planner-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouteBadge, StateView, StopTimeView, StationNamePipe],
  templateUrl: './planner-page.html',
  styleUrl: './planner-page.scss',
})
export class PlannerPage {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);

  /** Optional ?from=&to= (e.g. "Plan from here" on a station board) override the remembered pair. */
  readonly from = input<string>();
  readonly to = input<string>();

  protected readonly fromId = signal('');
  protected readonly toId = signal('');
  protected readonly mode = signal<'now' | 'at'>('now');
  protected readonly at = signal('');
  protected readonly limit = signal(PAGE);

  protected readonly stations = this.op.stations;
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
    // Restore the pair once per operator, when the station list arrives.
    effect(() => {
      const list = this.stations.data();
      const code = this.op.code();
      if (!list || this.restoredFor === code) return;
      this.restoredFor = code;
      const fromQuery = untracked(this.from);
      const toQuery = untracked(this.to);
      const remembered = readJson<Partial<StationPair> | null>(STORAGE_KEYS.trip(code), null);
      let wanted: Partial<StationPair> = {
        from: fromQuery || remembered?.from,
        to: toQuery || remembered?.to,
      };
      // "Plan from here" at the station you last went *to*: flip the remembered trip.
      if (fromQuery && !toQuery && wanted.to === fromQuery) wanted = { from: fromQuery, to: remembered?.from };
      const pair = sanitizePair(list, wanted);
      this.fromId.set(pair.from);
      this.toId.set(pair.to);
    });

    // Remember the pair as it changes.
    effect(() => {
      const pair = { from: this.fromId(), to: this.toId() };
      const code = this.op.code();
      if (this.restoredFor !== code) return;
      writeJson(STORAGE_KEYS.trip(code), pair);
    });
  }

  protected setFrom(id: string): void {
    this.fromId.set(id);
    this.limit.set(PAGE);
  }

  protected setTo(id: string): void {
    this.toId.set(id);
    this.limit.set(PAGE);
  }

  protected swap(): void {
    const s = swapPair({ from: this.fromId(), to: this.toId() });
    this.fromId.set(s.from);
    this.toId.set(s.to);
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

  /** The planner only finds direct trains; an empty result usually means a transfer. */
  protected noDirectMessage(p: PlanResponse): string {
    const msg =
      `No single train runs from ${stationName(p.from.name)} to ${stationName(p.to.name)}. ` +
      'This trip may need a transfer.';
    return this.op.code() === 'CT'
      ? `${msg} South County trains (Tamien to Gilroy) connect with the main line at San Jose Diridon.`
      : msg;
  }

  protected readonly duration = formatDuration;
  protected readonly stopsText = stopsText;
}
