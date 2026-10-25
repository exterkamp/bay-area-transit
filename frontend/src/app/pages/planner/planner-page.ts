import { HttpClient, httpResource } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import type { AgencyId, Place, PlanResponse, PlanTrip, Route } from '../../api/models';
import { apiUrls, withoutParam } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { delayInfo } from '../../lib/delay';
import { compareAgencies, tripLabel } from '../../lib/agencies';
import { fareLabel, stationName, stopsText } from '../../lib/format';
import { legacyPairIds, readPair } from '../../lib/places';
import { PlanScope, chooseScope, needsLine, readPlan, routeLabel, sortRoutes } from '../../lib/plan-scope';
import { STORAGE_KEYS, readJson, writeJson } from '../../lib/storage';
import { countdown, formatDuration, formatInstant, nowInZone } from '../../lib/time';
import { RouteBadge } from '../../shared/route-badge';
import { StateView } from '../../shared/state';
import { StationNamePipe } from '../../shared/station-name.pipe';
import { StopTimeView } from '../../shared/stop-time';

const PAGE = 10;
const MAX_LIMIT = 50;

/**
 * Trips planned on one agency at a time: pick it, then the stations it calls
 * at fill the dropdowns. Agencies too big for one list (Muni, SamTrans) ask
 * for a line first and list its stops.
 */
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
  private readonly http = inject(HttpClient);

  /** Optional ?from=&to= place ids (e.g. "Plan from here" on a board) override the remembered plan. */
  readonly from = input<string>();
  readonly to = input<string>();

  protected readonly agency = signal<AgencyId | null>(null);
  protected readonly route = signal<string | null>(null);
  protected readonly fromId = signal('');
  protected readonly toId = signal('');
  /** The operator whose remembered plan has been restored (restoring may need a fetch). */
  protected readonly restored = signal('');
  protected readonly mode = signal<'now' | 'at'>('now');
  protected readonly at = signal('');
  protected readonly limit = signal(PAGE);

  private restoredFor = '';

  protected readonly agencies = computed(() =>
    [...(this.op.agencies.data() ?? [])].sort((a, b) => compareAgencies(a.id, b.id)),
  );
  private readonly agencyInfo = computed(() => this.agencies().find((a) => a.id === this.agency()));
  protected readonly lineFirst = computed(() => needsLine(this.agencyInfo()));

  private readonly routes = httpResource<Route[]>(() => {
    const agency = this.agency();
    return agency && this.lineFirst() ? apiUrls.routes(this.op.code(), { agency }) : undefined;
  });
  protected readonly lines = computed(() => sortRoutes(this.routes.hasValue() ? this.routes.value() : []));

  protected readonly stations = httpResource<Place[]>(() => {
    const agency = this.agency();
    if (!agency || !this.agencyInfo()) return undefined;
    if (!this.lineFirst()) return apiUrls.stations(this.op.code(), { agency });
    const route = this.route();
    return route ? apiUrls.stations(this.op.code(), { route }) : undefined;
  });
  protected readonly stationList = computed(() => (this.stations.hasValue() ? this.stations.value() : []));
  /** What to call the places in the dropdowns: a big agency's are mostly street stops. */
  protected readonly placeNoun = computed(() => (this.lineFirst() ? 'stop' : 'station'));

  protected readonly placeholder = computed(() => {
    if (this.lineFirst() && !this.route()) return 'Choose a line first';
    if (this.stations.isLoading()) return `Loading ${this.placeNoun()}s…`;
    return `Choose a ${this.placeNoun()}`;
  });

  protected readonly sameStation = computed(() => !!this.fromId() && this.fromId() === this.toId());

  private readonly planUrl = computed(() => {
    const from = this.fromId();
    const to = this.toId();
    const agency = this.agency();
    const route = this.lineFirst() ? this.route() : null;
    if (!from || !to || from === to || !agency || (this.lineFirst() && !route) || this.op.noFeed()) return undefined;
    const at = this.mode() === 'at' && this.at() ? this.at() : null;
    return apiUrls.plan(this.op.code(), { from, to, at, limit: this.limit(), ...(route ? { route } : { agency }) });
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
    // Restore the plan once per operator, once its agencies are known.
    effect(() => {
      const code = this.op.code();
      if (!this.op.feed() || !this.op.agencies.data() || this.restoredFor === code) return;
      this.restoredFor = code;
      untracked(() => void this.restore(code));
    });

    // A new agency or line keeps the places it also calls at, and drops the rest.
    effect(() => {
      if (this.stations.status() !== 'resolved') return;
      const ids = new Set(this.stationList().map((p) => p.id));
      untracked(() => {
        if (this.fromId() && !ids.has(this.fromId())) this.fromId.set('');
        if (this.toId() && !ids.has(this.toId())) this.toId.set('');
      });
    });

    // Remember the plan as it changes.
    effect(() => {
      const plan = { agency: this.agency(), route: this.route(), from: this.fromId(), to: this.toId() };
      const code = this.op.code();
      if (this.restored() !== code) return;
      writeJson(STORAGE_KEYS.plan(code), plan);
    });
  }

  private async restore(code: string): Promise<void> {
    const saved = readPlan(readJson(STORAGE_KEYS.plan(code), null));
    let { from, to } = saved;
    if (!saved.agency && !from && !to) {
      // Before plans were per agency: the last pair of places, or the Caltrain-only app's.
      const pair = readPair(readJson(STORAGE_KEYS.trip(code), null));
      from = pair.from?.id ?? '';
      to = pair.to?.id ?? '';
      if (!from && !to && code === 'RG') {
        const legacy = legacyPairIds(readJson(STORAGE_KEYS.legacyTrip, null));
        from = legacy?.from ?? '';
        to = legacy?.to ?? '';
      }
    }
    const fromQuery = untracked(this.from);
    const toQuery = untracked(this.to);
    if (fromQuery && from !== fromQuery) {
      // "Plan from here" at the place you last went *to*: flip the remembered trip.
      if (!toQuery && to === fromQuery) to = from;
      from = fromQuery;
    }
    if (toQuery && to !== toQuery) to = toQuery;

    const agencies = this.op.agencies.data() ?? [];
    let scope: PlanScope = { agency: saved.agency, route: saved.route };
    const known = agencies.find((a) => a.id === scope.agency);
    if (fromQuery || toQuery || !known || (needsLine(known) && !scope.route)) {
      // Work the agency (and line) out from the places themselves.
      const [f, t] = await Promise.all([this.lookup(code, from), this.lookup(code, to)]);
      scope = chooseScope(f, t, agencies, scope);
      from = f?.id ?? '';
      to = t?.id ?? '';
    }
    if (this.op.code() !== code) return;
    this.agency.set(scope.agency);
    this.route.set(scope.route);
    this.fromId.set(from);
    this.toId.set(to && to !== from ? to : '');
    this.restored.set(code);
  }

  private async lookup(code: string, id: string): Promise<Place | null> {
    if (!id) return null;
    try {
      return await firstValueFrom(this.http.get<Place>(apiUrls.place(code, id)));
    } catch {
      return null;
    }
  }

  protected setAgency(id: AgencyId): void {
    if (id === this.agency()) return;
    this.agency.set(id);
    this.route.set(null);
    this.limit.set(PAGE);
  }

  protected setRoute(id: string): void {
    this.route.set(id || null);
    this.limit.set(PAGE);
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
    const from = this.fromId();
    this.fromId.set(this.toId());
    this.toId.set(from);
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
      `No ${this.scopeName()} trip runs straight from ${from} to ${to}. ` +
      "It may need a transfer, and the planner doesn't plan those yet. The departure boards at each end show what leaves from where."
    );
  }

  /** "Caltrain", or "SamTrans ECR" when planning on one line. */
  private scopeName(): string {
    const agency = this.agency();
    const name = agency ? this.op.agencyName(agency) : '';
    const line = this.lineFirst() ? this.lines().find((r) => r.id === this.route()) : undefined;
    return line ? `${name} ${line.short_name || line.long_name}` : name;
  }

  protected readonly duration = formatDuration;
  protected readonly routeLabel = routeLabel;
  protected readonly tripLabel = tripLabel;
  protected readonly stopsText = stopsText;
}
