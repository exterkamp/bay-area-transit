// Fixtures shaped exactly like docs/api.md's examples. Specs only.

import type {
  Alert,
  Departure,
  Operator,
  Place,
  PlanResponse,
  RouteRef,
} from '../app/api/models';

export const operatorCT: Operator = {
  code: 'CT',
  name: 'Caltrain',
  timezone: 'America/Los_Angeles',
  feed: {
    version: '20260922',
    start_date: '2026-01-31',
    end_date: '2027-01-31',
    imported_at: '2026-10-24T03:00:12-07:00',
  },
  realtime: {
    trip_updates_at: '2026-10-24T08:14:02-07:00',
    vehicle_positions_at: '2026-10-24T08:14:05-07:00',
    alerts_at: '2026-10-24T08:10:00-07:00',
  },
  agencies: ['CT'],
};

export const limited: RouteRef = {
  id: 'Limited',
  short_name: 'Limited',
  color: '#99d7dc',
  text_color: '#000000',
  agency: 'CT',
  type: 2,
};

export const powell: Place = {
  id: 'mtc:powell',
  name: 'Powell',
  kind: 'station',
  lat: 37.78445,
  lon: -122.40792,
  zone: '',
  wheelchair_boarding: 'unknown',
  agencies: ['BA', 'SF'],
  routes: [
    { id: 'BA:Red-N', short_name: 'Red-N', color: '#ed1c24', text_color: '#ffffff', agency: 'BA', type: 1 },
    { id: 'SF:N', short_name: 'N', color: '#005b95', text_color: '#ffffff', agency: 'SF', type: 0 },
  ],
  platforms: [{ id: '16995', name: 'Powell Station Outbound', platform_code: '' }],
};

export const plan: PlanResponse = {
  from: { id: 'palo_alto', name: 'Palo Alto' },
  to: { id: 'san_francisco', name: 'San Francisco' },
  at: '2026-10-24T08:00:00-07:00',
  fare: { price: '6.75', currency: 'USD' },
  trips: [
    {
      trip_id: '401',
      service_date: '2026-10-24',
      short_name: '401',
      headsign: 'San Francisco',
      direction: 0,
      route: limited,
      status: 'scheduled',
      depart: {
        stop_id: '70171',
        platform: 'Palo Alto Caltrain Station Northbound',
        scheduled: '2026-10-24T08:05:00-07:00',
        estimated: '2026-10-24T08:07:00-07:00',
        delay_seconds: 120,
      },
      arrive: {
        stop_id: '70011',
        platform: 'San Francisco Caltrain Station',
        scheduled: '2026-10-24T08:52:00-07:00',
        estimated: null,
        delay_seconds: null,
      },
      duration_minutes: 47,
      stops_between: 6,
    },
  ],
};

export function dep(
  tripId: string,
  direction: number,
  dest: [string, string],
  headsign: string,
  route: Partial<RouteRef> = {},
): Departure {
  return {
    trip_id: tripId,
    service_date: '2026-10-24',
    short_name: tripId,
    headsign,
    direction,
    route: { id: 'Local', short_name: 'Local', color: '#eeeeee', text_color: '#000000', agency: 'CT', type: 2, ...route },
    status: 'live',
    depart: {
      stop_id: '70171',
      platform: 'Palo Alto',
      scheduled: '2026-10-24T08:05:00-07:00',
      estimated: null,
      delay_seconds: null,
    },
    destination: { id: dest[0], name: dest[1] },
  };
}

export const departures: Departure[] = [
  dep('402', 1, ['san_jose_diridon', 'San Jose Diridon'], 'San Jose Diridon'),
  dep('401', 0, ['san_francisco', 'San Francisco'], 'San Francisco'),
  dep('404', 1, ['san_jose_diridon', 'San Jose Diridon'], 'San Jose Diridon'),
  dep('403', 0, ['22nd_street', '22nd Street'], 'San Francisco'),
];

export const alert: Alert = {
  id: 'alert-123',
  header: 'Delays near Millbrae',
  description: 'Trains are running up to 15 minutes late.',
  url: '',
  cause: 'technical_problem',
  effect: 'significant_delays',
  active_periods: [{ start: '2026-10-24T07:30:00-07:00', end: null }],
  route_ids: ['Local Weekday'],
  stop_ids: ['70111'],
  agencies: ['CT'],
};
