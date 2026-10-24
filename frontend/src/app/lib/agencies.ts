// Agency display names and vehicle words. Framework-free.

import type { AgencyId, RouteRef, Vehicle } from '../api/models';

/** What riders call each agency of 511's regional feed. */
const SHORT_NAMES: Record<AgencyId, string> = {
  SF: 'Muni',
  BA: 'BART',
  SM: 'SamTrans',
  CT: 'Caltrain',
};

/** The order agencies are listed in, wherever several appear together. */
export const AGENCY_ORDER: readonly AgencyId[] = ['SF', 'BA', 'SM', 'CT'];

export function agencyName(id: AgencyId, fullName?: string): string {
  return SHORT_NAMES[id] ?? fullName ?? id;
}

export function compareAgencies(a: AgencyId, b: AgencyId): number {
  const rank = (id: AgencyId) => {
    const i = AGENCY_ORDER.indexOf(id);
    return i < 0 ? AGENCY_ORDER.length : i;
  };
  return rank(a) - rank(b) || a.localeCompare(b);
}

/** "Train", "Bus" or "Cable car", from the GTFS route type. */
export function vehicleNoun(route: Pick<RouteRef, 'type'> | null | undefined): string {
  switch (route?.type) {
    case 3:
    case 11:
      return 'Bus';
    case 5:
      return 'Cable car';
    case 4:
      return 'Ferry';
    default:
      return 'Train';
  }
}

/**
 * "Train 401" when the trip has a real number; the API falls back to the
 * trip id when the feed has none (Muni, BART), and a trip id means nothing
 * to a rider.
 */
export function tripLabel(t: { trip_id: string; short_name: string; route: RouteRef | null }): string {
  const noun = vehicleNoun(t.route);
  return t.short_name && t.short_name !== t.trip_id ? `${noun} ${t.short_name}` : noun;
}

/**
 * A stable id for a vehicle marker: the vehicle's own id, else its trip's.
 * Estimates always go by trip: they're one per trip, and the ids feeds put in
 * trip updates aren't always unique.
 */
export function vehicleKey(v: Pick<Vehicle, 'vehicle_id' | 'trip_id' | 'source'>): string {
  return v.source === 'gps' && v.vehicle_id ? v.vehicle_id : `trip:${v.trip_id}`;
}
