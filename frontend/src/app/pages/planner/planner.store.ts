import { HttpClient, httpResource } from '@angular/common/http';
import { computed, effect, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withHooks, withMethods, withProps, withState } from '@ngrx/signals';
import { rxMethod } from '@ngrx/signals/rxjs-interop';
import { Observable, catchError, distinctUntilChanged, filter, forkJoin, map, of, pipe, switchMap, tap } from 'rxjs';
import type { AgencyId, Place, PlanResponse, Route } from '../../api/models';
import { apiUrls, withoutParam } from '../../api/urls';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { compareAgencies } from '../../lib/agencies';
import { fareLabel } from '../../lib/format';
import { RememberedPlan, chooseScope, needsLine, rememberedPlan, sortRoutes, withQuery } from '../../lib/plan-scope';
import { STORAGE_KEYS, readJson, writeJson } from '../../lib/storage';
import { formatInstant, nowInZone } from '../../lib/time';

const PAGE = 10;
const MAX_LIMIT = 50;

/** What restoring a plan needs: an operator whose agencies are known, and the link's ?from=&to=. */
export interface PlanQuery {
  code: string;
  from?: string;
  to?: string;
}

interface PlannerState {
  agency: AgencyId | null;
  route: string | null;
  /** As picked; `fromId`/`toId` drop one the agency (or line) doesn't call at. */
  from: string;
  to: string;
  mode: 'now' | 'at';
  at: string;
  limit: number;
  /** The operator whose remembered plan has been restored (restoring may need a fetch). */
  restoredFor: string;
}

/**
 * One trip planner's state: the agency and line, the places, when, and the
 * plan for them. Provided by the planner page, so it lives as long as it.
 */
export const PlannerStore = signalStore(
  withState<PlannerState>({
    agency: null,
    route: null,
    from: '',
    to: '',
    mode: 'now',
    at: '',
    limit: PAGE,
    restoredFor: '',
  }),
  withProps(() => ({ _op: inject(OperatorService), _http: inject(HttpClient) })),
  withComputed(({ agency, _op }) => {
    const agencies = computed(() => [...(_op.agencies.data() ?? [])].sort((a, b) => compareAgencies(a.id, b.id)));
    const agencyInfo = computed(() => agencies().find((a) => a.id === agency()));
    return {
      agencies,
      _agencyInfo: agencyInfo,
      /** Too many places for one list (Muni, SamTrans): pick a line, then its stops. */
      lineFirst: computed(() => needsLine(agencyInfo())),
      /** The operator, once restoring a plan for it can start. */
      readyCode: computed(() => (_op.feed() && _op.agencies.data() ? _op.code() : null)),
    };
  }),
  withProps(({ agency, route, lineFirst, _agencyInfo, _op }) => ({
    _routes: httpResource<Route[]>(() => {
      const a = agency();
      return a && lineFirst() ? apiUrls.routes(_op.code(), { agency: a }) : undefined;
    }),
    _stations: httpResource<Place[]>(() => {
      const a = agency();
      if (!a || !_agencyInfo()) return undefined;
      if (!lineFirst()) return apiUrls.stations(_op.code(), { agency: a });
      const r = route();
      return r ? apiUrls.stations(_op.code(), { route: r }) : undefined;
    }),
  })),
  withComputed(({ from, to, agency, route, lineFirst, mode, at, limit, restoredFor, _routes, _stations, _op }) => {
    const stationList = computed(() => (_stations.hasValue() ? _stations.value() : []));
    const served = computed(() => (_stations.hasValue() ? new Set(stationList().map((p) => p.id)) : null));
    // A new agency or line keeps the places it also calls at. Until its list
    // is in, the picks stand.
    const pick = (id: string) => (served()?.has(id) ?? true ? id : '');
    const fromId = computed(() => pick(from()));
    const toId = computed(() => pick(to()));
    const lines = computed(() => sortRoutes(_routes.hasValue() ? _routes.value() : []));
    const placeNoun = computed(() => (lineFirst() ? 'stop' : 'station'));
    return {
      lines,
      stationList,
      stationsError: computed(() => !!_stations.error()),
      fromId,
      toId,
      /** What to call the places in the dropdowns: a big agency's are mostly street stops. */
      placeNoun,
      placeholder: computed(() => {
        if (lineFirst() && !route()) return 'Choose a line first';
        if (_stations.isLoading()) return `Loading ${placeNoun()}s…`;
        return `Choose a ${placeNoun()}`;
      }),
      sameStation: computed(() => !!fromId() && fromId() === toId()),
      restored: computed(() => restoredFor() === _op.code()),
      /** "Caltrain", or "SamTrans ECR" when planning on one line. */
      scopeName: computed(() => {
        const a = agency();
        const name = a ? _op.agencyName(a) : '';
        const line = lineFirst() ? lines().find((r) => r.id === route()) : undefined;
        return line ? `${name} ${line.short_name || line.long_name}` : name;
      }),
      _planUrl: computed(() => {
        const f = fromId();
        const t = toId();
        const a = agency();
        const r = lineFirst() ? route() : null;
        if (!f || !t || f === t || !a || (lineFirst() && !r) || _op.noFeed()) return undefined;
        const when = mode() === 'at' && at() ? at() : null;
        return apiUrls.plan(_op.code(), { from: f, to: t, at: when, limit: limit(), ...(r ? { route: r } : { agency: a }) });
      }),
    };
  }),
  withProps(({ _planUrl, mode }) => ({
    plan: polled<PlanResponse>(() => _planUrl(), {
      intervalMs: 60_000,
      enabled: () => mode() === 'now',
      what: 'that trip',
      keepPreviousWhile: (a, b) => withoutParam(a, 'limit') === withoutParam(b, 'limit'),
    }),
  })),
  withComputed(({ plan, limit, _op }) => ({
    fare: computed(() => fareLabel(plan.data()?.fare)),
    updated: computed(() => {
      const t = plan.updatedAt();
      return t ? formatInstant(t, _op.timeZone()) : '';
    }),
    canShowMore: computed(() => {
      const p = plan.data();
      return !!p && p.trips.length >= limit() && limit() < MAX_LIMIT;
    }),
  })),
  withMethods((store) => {
    const lookup = (code: string, id: string): Observable<Place | null> =>
      id ? store._http.get<Place>(apiUrls.place(code, id)).pipe(catchError(() => of(null))) : of(null);

    /** The remembered plan with the link's places, its agency (and line) worked out from them if need be. */
    const resolve = (q: PlanQuery): Observable<RememberedPlan> => {
      const saved = rememberedPlan(q.code, {
        plan: readJson(STORAGE_KEYS.plan(q.code), null),
        trip: readJson(STORAGE_KEYS.trip(q.code), null),
        legacyTrip: readJson(STORAGE_KEYS.legacyTrip, null),
      });
      const { from, to } = withQuery(saved, q);
      const agencies = store.agencies();
      const known = agencies.find((a) => a.id === saved.agency);
      if (!q.from && !q.to && known && (!needsLine(known) || saved.route)) return of({ ...saved, from, to });
      return forkJoin([lookup(q.code, from), lookup(q.code, to)]).pipe(
        map(([f, t]) => ({ ...chooseScope(f, t, agencies, saved), from: f?.id ?? '', to: t?.id ?? '' })),
      );
    };

    return {
      /** Restore once per operator, as soon as it's ready; a newer operator cancels an older one's lookups. */
      restore: rxMethod<PlanQuery | null>(
        pipe(
          filter((q): q is PlanQuery => !!q),
          distinctUntilChanged((a, b) => a.code === b.code),
          switchMap((q) =>
            resolve(q).pipe(
              tap(({ agency, route, from, to }) =>
                patchState(store, { agency, route, from, to: to !== from ? to : '', restoredFor: q.code }),
              ),
            ),
          ),
        ),
      ),
      setAgency(agency: AgencyId): void {
        if (agency !== store.agency()) patchState(store, { agency, route: null, limit: PAGE });
      },
      setRoute(route: string): void {
        patchState(store, { route: route || null, limit: PAGE });
      },
      setFrom(from: string): void {
        patchState(store, { from, limit: PAGE });
      },
      setTo(to: string): void {
        patchState(store, { to, limit: PAGE });
      },
      swap(): void {
        patchState(store, { from: store.toId(), to: store.fromId(), limit: PAGE });
      },
      setMode(mode: 'now' | 'at'): void {
        patchState(store, (s) => ({
          mode,
          at: mode === 'at' && !s.at ? nowInZone(store._op.timeZone()) : s.at,
          limit: PAGE,
        }));
      },
      setAt(at: string): void {
        patchState(store, { at, limit: PAGE });
      },
      more(): void {
        patchState(store, (s) => ({ limit: Math.min(MAX_LIMIT, s.limit + PAGE) }));
      },
      reloadStations(): void {
        store._stations.reload();
      },
    };
  }),
  withHooks({
    onInit(store) {
      // Remember the plan as it changes, once the remembered one is back.
      effect(() => {
        const plan = { agency: store.agency(), route: store.route(), from: store.fromId(), to: store.toId() };
        const code = store._op.code();
        if (store.restoredFor() === code) writeJson(STORAGE_KEYS.plan(code), plan);
      });
    },
  }),
);
