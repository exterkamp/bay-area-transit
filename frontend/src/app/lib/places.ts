// Place helpers: remembered trips, recent picks, departure groups. Framework-free.

import type { AgencyId, Departure, Place } from '../api/models';
import { compareAgencies } from './agencies';

/** Enough of a place to show and re-request it without a lookup. */
export interface PlaceRef {
  id: string;
  name: string;
  agencies: AgencyId[];
}

export interface PlacePair {
  from: PlaceRef | null;
  to: PlaceRef | null;
}

export function placeRef(p: Pick<Place, 'id' | 'name' | 'agencies'>): PlaceRef {
  return { id: p.id, name: p.name, agencies: [...p.agencies] };
}

export function swapPair(p: PlacePair): PlacePair {
  return { from: p.to, to: p.from };
}

function isRef(v: unknown): v is PlaceRef {
  const r = v as PlaceRef;
  return !!r && typeof r === 'object' && typeof r.id === 'string' && !!r.id && typeof r.name === 'string';
}

function asRef(v: unknown): PlaceRef | null {
  return isRef(v) ? { id: v.id, name: v.name, agencies: Array.isArray(v.agencies) ? v.agencies.filter((a) => typeof a === 'string') : [] } : null;
}

/** A remembered pair as stored, defensively: junk becomes null, the same place twice drops `to`. */
export function readPair(raw: unknown): PlacePair {
  const r = (raw ?? {}) as Record<string, unknown>;
  const from = asRef(r['from']);
  let to = asRef(r['to']);
  if (from && to && from.id === to.id) to = null;
  return { from, to };
}

/**
 * Caltrain station ids from the old single-agency feed whose regional ids
 * differ. Every other Caltrain id carried over unchanged.
 */
export const LEGACY_CALTRAIN_IDS: Readonly<Record<string, string>> = {
  san_francisco: 'mtc:caltrain-4th-&-king',
  place_MLBR: 'mtc:millbrae-bart',
  palo_alto: 'mtc:palo-alto-station',
  mountain_view: 'mtc:mountain-view-station',
  santa_clara: 'mtc:santa-clara-caltrain',
  sj_diridon: 'mtc:san-jose-diridon-station',
};

/**
 * The pair the Caltrain-only app remembered, `{from: id, to: id}`, as place
 * ids in the regional feed. Names are unknown until the places are fetched.
 */
export function legacyPairIds(raw: unknown): { from: string; to: string } | null {
  const r = (raw ?? {}) as Record<string, unknown>;
  const id = (v: unknown) => (typeof v === 'string' && v ? (LEGACY_CALTRAIN_IDS[v] ?? v) : '');
  const from = id(r['from']);
  const to = id(r['to']);
  if (!from && !to) return null;
  return { from, to: to === from ? '' : to };
}

export const MAX_RECENTS = 6;

/** Most recent first, no duplicates. */
export function addRecent(list: readonly PlaceRef[], place: PlaceRef, max = MAX_RECENTS): PlaceRef[] {
  return [place, ...list.filter((p) => p.id !== place.id)].slice(0, max);
}

export function readRecents(raw: unknown): PlaceRef[] {
  return Array.isArray(raw) ? raw.map(asRef).filter((p): p is PlaceRef => !!p).slice(0, MAX_RECENTS) : [];
}

/** What each agency calls its GTFS directions, where that's consistent. */
const DIRECTION_NAMES: Record<AgencyId, Record<number, string>> = {
  CT: { 0: 'Northbound', 1: 'Southbound' },
  SF: { 0: 'Outbound', 1: 'Inbound' },
};

export interface DepartureGroup {
  agency: AgencyId;
  direction: number;
  /** "Northbound", or "Toward Richmond · Antioch" where directions have no name. */
  label: string;
  /** The most common destinations, when the label doesn't already say them. */
  detail: string;
  departures: Departure[];
}

/**
 * Split a board by agency and GTFS direction, keeping API (time) order
 * within each. Agencies come in AGENCY_ORDER, directions by id.
 */
export function groupDepartures(departures: readonly Departure[]): DepartureGroup[] {
  const groups = new Map<string, DepartureGroup>();
  for (const d of departures) {
    const agency = d.route.agency;
    const key = `${agency}|${d.direction}`;
    let g = groups.get(key);
    if (!g) {
      g = { agency, direction: d.direction, label: '', detail: '', departures: [] };
      groups.set(key, g);
    }
    g.departures.push(d);
  }
  for (const g of groups.values()) {
    const where = topValues(g.departures.map((d) => d.headsign || d.destination.name), 2);
    const named = DIRECTION_NAMES[g.agency]?.[g.direction];
    g.label = named ?? `Toward ${where.join(' · ')}`;
    g.detail = named ? `to ${where.join(', ')}` : '';
  }
  return [...groups.values()].sort((a, b) => compareAgencies(a.agency, b.agency) || a.direction - b.direction);
}

/** The `n` most frequent values, most frequent first, first seen on ties. */
export function topValues(values: readonly string[], n: number): string[] {
  const counts = new Map<string, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts.entries()]
    .map(([value, count], order) => ({ value, count, order }))
    .sort((a, b) => b.count - a.count || a.order - b.order)
    .slice(0, n)
    .map((e) => e.value);
}

/** "120 m" / "1.4 km". */
export function formatDistance(meters: number): string {
  if (meters < 950) return `${Math.max(10, Math.round(meters / 10) * 10)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}
