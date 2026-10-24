// Station list helpers. Framework-free.
//
// The API returns stations ordered north to south along the line (docs/api.md),
// so the list's own order is the geography and is never re-sorted here.

import type { Departure, Station } from '../api/models';

export interface StationPair {
  from: string;
  to: string;
}

export function indexById(stations: readonly Station[]): Map<string, number> {
  const m = new Map<string, number>();
  stations.forEach((s, i) => m.set(s.id, i));
  return m;
}

export function findStation(stations: readonly Station[], id: string | null | undefined): Station | undefined {
  if (!id) return undefined;
  return stations.find((s) => s.id === id);
}

/** Look a station up by one of its platform (child stop) ids. */
export function stationForPlatform(stations: readonly Station[], stopId: string | null | undefined): Station | undefined {
  if (!stopId) return undefined;
  return stations.find((s) => s.id === stopId || s.platforms.some((p) => p.id === stopId));
}

export function swapPair(p: StationPair): StationPair {
  return { from: p.to, to: p.from };
}

/**
 * Keep only the parts of a remembered pair that still name a station in the
 * current list, and never the same station twice.
 */
export function sanitizePair(
  stations: readonly Station[],
  p: Partial<StationPair> | null | undefined,
): StationPair {
  const ids = new Set(stations.map((s) => s.id));
  const from = p?.from && ids.has(p.from) ? p.from : '';
  let to = p?.to && ids.has(p.to) ? p.to : '';
  if (to && to === from) to = '';
  return { from, to };
}

export type Heading = 'north' | 'south';

/**
 * Which way a trip from `fromId` to `toId` heads, by list order (the list is
 * north-to-south). null if either station is off the ordered line or they're
 * the same.
 */
export function heading(stations: readonly Station[], fromId: string, toId: string): Heading | null {
  const idx = indexById(stations);
  const a = idx.get(fromId);
  const b = idx.get(toId);
  if (a == null || b == null || a === b) return null;
  return b < a ? 'north' : 'south';
}

export interface DepartureGroup {
  direction: number;
  /** "Northbound" / "Southbound" when the order says so, else "Toward <most common headsign>". */
  label: string;
  departures: Departure[];
}

/**
 * Split a station's board by GTFS direction, keeping API order within each.
 * Groups are ordered northbound first when the heading is known, else by
 * direction id.
 */
export function groupByDirection(
  stations: readonly Station[],
  stationId: string,
  departures: readonly Departure[],
): DepartureGroup[] {
  const byDir = new Map<number, Departure[]>();
  for (const d of departures) {
    const list = byDir.get(d.direction) ?? [];
    list.push(d);
    byDir.set(d.direction, list);
  }
  const groups: (DepartureGroup & { sortKey: number })[] = [];
  for (const [direction, list] of byDir) {
    const headings = list.map((d) => heading(stations, stationId, d.destination.id));
    const known = headings.find((h) => h != null) ?? null;
    const label = known
      ? known === 'north'
        ? 'Northbound'
        : 'Southbound'
      : `Toward ${mostCommon(list.map((d) => d.headsign || d.destination.name))}`;
    groups.push({
      direction,
      label,
      departures: list,
      sortKey: known === 'north' ? -1 : known === 'south' ? 1 : direction,
    });
  }
  groups.sort((a, b) => a.sortKey - b.sortKey || a.direction - b.direction);
  return groups.map(({ sortKey: _s, ...g }) => g);
}

export function mostCommon(values: readonly string[]): string {
  const counts = new Map<string, number>();
  let best = '';
  let bestN = 0;
  for (const v of values) {
    const n = (counts.get(v) ?? 0) + 1;
    counts.set(v, n);
    if (n > bestN) {
      best = v;
      bestN = n;
    }
  }
  return best;
}
