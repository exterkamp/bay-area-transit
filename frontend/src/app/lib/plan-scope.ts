// Which agency, and which of its lines, a trip is planned on. Framework-free.

import type { Agency, AgencyId, Place, Route } from '../api/models';
import { compareAgencies } from './agencies';
import { legacyPairIds, readPair } from './places';

/**
 * Agencies calling at more places than this (Muni's 257 stops, SamTrans's
 * 1,400) are too long for one dropdown: you pick a line, then its stops.
 */
export const LINE_FIRST_OVER = 100;

export interface PlanScope {
  agency: AgencyId | null;
  /** Set only for an agency that needs a line first. */
  route: string | null;
}

export interface RememberedPlan extends PlanScope {
  from: string;
  to: string;
}

export function needsLine(agency: Pick<Agency, 'places'> | null | undefined): boolean {
  return !!agency && agency.places > LINE_FIRST_OVER;
}

/** A remembered plan as stored, defensively: junk becomes empty. */
export function readPlan(raw: unknown): RememberedPlan {
  const r = (raw ?? {}) as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === 'string' ? v : '');
  const from = str(r['from']);
  const to = str(r['to']);
  return { agency: str(r['agency']) || null, route: str(r['route']) || null, from, to: to === from ? '' : to };
}

/**
 * The plan remembered for an operator, as stored under `plan`; else the
 * places from before plans were per agency (`trip`), else the Caltrain-only
 * app's (`legacyTrip`, regional feed only).
 */
export function rememberedPlan(
  code: string,
  stored: { plan: unknown; trip: unknown; legacyTrip: unknown },
): RememberedPlan {
  const saved = readPlan(stored.plan);
  if (saved.agency || saved.from || saved.to) return saved;
  const pair = readPair(stored.trip);
  let from = pair.from?.id ?? '';
  let to = pair.to?.id ?? '';
  if (!from && !to && code === 'RG') {
    const legacy = legacyPairIds(stored.legacyTrip);
    from = legacy?.from ?? '';
    to = legacy?.to ?? '';
  }
  return { ...saved, from, to: to === from ? '' : to };
}

/**
 * ?from=&to= on the link (e.g. "Plan from here" on a board) over the
 * remembered places. "Plan from here" at the place you last went *to*
 * flips the remembered trip.
 */
export function withQuery(
  saved: { from: string; to: string },
  query: { from?: string; to?: string },
): { from: string; to: string } {
  let { from, to } = saved;
  if (query.from && from !== query.from) {
    if (!query.to && to === query.from) to = from;
    from = query.from;
  }
  if (query.to) to = query.to;
  return { from, to: to === from ? '' : to };
}

/** Lines by name, numbers in numeric order: 1, 2, 10, ECR. */
export function sortRoutes(routes: readonly Route[]): Route[] {
  return [...routes].sort((a, b) => routeLabel(a).localeCompare(routeLabel(b), 'en', { numeric: true }));
}

export function routeLabel(r: Pick<Route, 'short_name' | 'long_name' | 'id'>): string {
  if (r.short_name && r.long_name && r.short_name !== r.long_name) return `${r.short_name} · ${r.long_name}`;
  return r.short_name || r.long_name || r.id;
}

/**
 * The scope for planning between two places: an agency serving both if
 * there is one (else either), the preferred one when it qualifies, else one
 * that needs no line, in the usual order; and for
 * a big agency, a line of it calling at both (else either).
 */
export function chooseScope(
  from: Pick<Place, 'agencies' | 'routes'> | null,
  to: Pick<Place, 'agencies' | 'routes'> | null,
  agencies: readonly Agency[],
  preferred: PlanScope,
): PlanScope {
  const known = new Map(agencies.map((a) => [a.id, a]));
  const both = (a: readonly string[] = [], b: readonly string[] = []) => a.filter((x) => b.includes(x));
  const pick = <T extends string>(options: T[][], wanted: T | null): T | null => {
    const list = options.find((o) => o.length) ?? [];
    return wanted && list.includes(wanted) ? wanted : (list[0] ?? null);
  };

  // Agencies listing their stations whole first: fewer steps than picking a line.
  const order = (a: AgencyId, b: AgencyId) =>
    Number(needsLine(known.get(a))) - Number(needsLine(known.get(b))) || compareAgencies(a, b);
  const fromAgencies = (from?.agencies ?? []).filter((a) => known.has(a)).sort(order);
  const toAgencies = (to?.agencies ?? []).filter((a) => known.has(a)).sort(order);
  let agency = pick([both(fromAgencies, toAgencies), fromAgencies, toAgencies], preferred.agency);
  if (!agency) {
    // Nothing to go on: the preferred agency, else the first that lists its stations whole.
    const all = [...known.values()].sort((a, b) => compareAgencies(a.id, b.id));
    agency = preferred.agency && known.has(preferred.agency) ? preferred.agency : (all.find((a) => !needsLine(a)) ?? all[0])?.id ?? null;
    return { agency, route: agency === preferred.agency && needsLine(known.get(agency)) ? preferred.route : null };
  }
  if (!needsLine(known.get(agency))) return { agency, route: null };

  const lines = (p: typeof from) => (p?.routes ?? []).filter((r) => r.agency === agency).map((r) => r.id);
  const route = pick([both(lines(from), lines(to)), lines(from), lines(to)], preferred.route);
  return { agency, route };
}
