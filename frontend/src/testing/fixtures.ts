// Fixtures shaped exactly like docs/api.md's examples. Specs only.

import type {
  Alert,
  Departure,
  Operator,
  PlanResponse,
  Station,
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
};

function station(id: string, name: string, lat: number, platforms: string[]): Station {
  return {
    id,
    name,
    lat,
    lon: -122.2,
    zone: '1',
    wheelchair_boarding: 'accessible',
    platforms: platforms.map((p) => ({ id: p, name: `${name} Caltrain Station`, platform_code: '' })),
  };
}

/** North to south, as the API orders them. */
export const stations: Station[] = [
  station('san_francisco', 'San Francisco', 37.776, ['70011', '70012']),
  station('22nd_street', '22nd Street', 37.757, ['70021', '70022']),
  station('millbrae', 'Millbrae', 37.6, ['70061', '70062']),
  station('palo_alto', 'Palo Alto', 37.443, ['70171', '70172']),
  station('san_jose_diridon', 'San Jose Diridon', 37.33, ['70261', '70262']),
  // Off the longest trip, so alphabetical at the end:
  station('college_park', 'College Park', 37.34, ['70251']),
];

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
      route: { id: 'Limited', short_name: 'Limited', color: '#99d7dc', text_color: '#000000' },
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

function dep(tripId: string, direction: number, dest: [string, string], headsign: string): Departure {
  return {
    trip_id: tripId,
    service_date: '2026-10-24',
    short_name: tripId,
    headsign,
    direction,
    route: { id: 'Local', short_name: 'Local', color: '#eeeeee', text_color: '#000000' },
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
};
