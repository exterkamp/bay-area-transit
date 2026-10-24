// Typed models of the API contract, docs/api.md (the source of truth).
// Everything the frontend reads from /api/v1 is described here and nowhere
// else. Field names match the JSON exactly; nothing is renamed on the way in.

/** ISO 8601 datetime with the agency's UTC offset, e.g. 2026-10-24T08:15:00-07:00. */
export type IsoDateTime = string;
/** YYYY-MM-DD. */
export type IsoDate = string;
/** 511 operator code, naming a data source: RG (the regional feed), CT, BA. */
export type OperatorCode = string;
/** GTFS agency_id within a feed: in RG, SF (Muni), BA, SM (SamTrans), CT. */
export type AgencyId = string;

export type ApiErrorCode = 'no_active_feed' | 'not_found' | 'bad_request' | 'filter_required';

/** Body of every 400/404. */
export interface ApiErrorBody {
  detail: string;
  code: ApiErrorCode;
}

export interface Health {
  status: 'ok';
}

// --- /operators -------------------------------------------------------------

export interface FeedInfo {
  version: string;
  start_date: IsoDate;
  end_date: IsoDate;
  imported_at: IsoDateTime;
}

export interface RealtimeInfo {
  trip_updates_at: IsoDateTime | null;
  vehicle_positions_at: IsoDateTime | null;
  alerts_at: IsoDateTime | null;
}

export interface Operator {
  code: OperatorCode;
  name: string;
  /** IANA zone, e.g. America/Los_Angeles. */
  timezone: string;
  /** null until a feed has been imported. */
  feed: FeedInfo | null;
  realtime: RealtimeInfo;
  agencies: AgencyId[];
}

// --- /agencies --------------------------------------------------------------

export interface Agency {
  id: AgencyId;
  name: string;
  url: string;
  timezone: string;
  /** GTFS route types: 0 light rail, 1 subway, 2 rail, 3 bus, 5 cable car. */
  route_types: number[];
}

// --- places (/places, /places/{id}, /stations) ------------------------------

export type WheelchairBoarding = 'unknown' | 'accessible' | 'inaccessible';

export interface Platform {
  id: string;
  name: string;
  platform_code: string;
}

/**
 * What a rider picks: a station with its platforms, or same-named stops on
 * both sides of a street. Any member stop id resolves to the place.
 */
export interface Place {
  id: string;
  name: string;
  kind: 'station' | 'stop';
  lat: number;
  lon: number;
  zone: string;
  wheelchair_boarding: WheelchairBoarding;
  agencies: AgencyId[];
  /** By agency, then name. */
  routes: RouteRef[];
  /** Where you board: a station's platforms, or the stops in a group. */
  platforms: Platform[];
  /** Only from a `near` search. */
  distance_m?: number;
}

export interface PlaceSearch {
  places: Place[];
}

// --- /routes ----------------------------------------------------------------

export interface Route {
  id: string;
  short_name: string;
  long_name: string;
  /** GTFS route_type; 2 = rail. */
  type: number;
  /** Always #rrggbb. */
  color: string;
  text_color: string;
  agency: AgencyId;
}

/** The compact route embedded in places, trips, departures and vehicles. */
export interface RouteRef {
  id: string;
  /** Falls back to the long name. */
  short_name: string;
  color: string;
  text_color: string;
  agency: AgencyId;
  type: number;
}

// --- /shapes (GeoJSON) ------------------------------------------------------

export interface ShapeProperties {
  route_id: string;
  color: string;
  agency: AgencyId;
}

export interface ShapeFeature {
  type: 'Feature';
  geometry: {
    type: 'LineString';
    /** [lon, lat] pairs. */
    coordinates: [number, number][];
  };
  properties: ShapeProperties;
}

export interface ShapeCollection {
  type: 'FeatureCollection';
  features: ShapeFeature[];
}

// --- trips: shared pieces ---------------------------------------------------

/** scheduled = no realtime for this trip; live = realtime present; canceled = trip or boarding stop canceled. */
export type TripStatus = 'scheduled' | 'live' | 'canceled';

/** A scheduled time plus its realtime estimate, if any. */
export interface StopTime {
  scheduled: IsoDateTime;
  estimated: IsoDateTime | null;
  delay_seconds: number | null;
}

/** A StopTime at a specific platform (plan/departures). */
export interface PlatformTime extends StopTime {
  stop_id: string;
  platform: string;
}

export interface StationRef {
  id: string;
  name: string;
}

interface TripBase {
  trip_id: string;
  service_date: IsoDate;
  short_name: string;
  headsign: string;
  direction: number;
  route: RouteRef;
  status: TripStatus;
}

// --- /plan ------------------------------------------------------------------

/** The base (adult) fare; discount categories aren't modelled. */
export interface Fare {
  /** Decimal string, e.g. "6.75". */
  price: string;
  currency: string;
}

export interface PlanTrip extends TripBase {
  depart: PlatformTime;
  arrive: PlatformTime;
  /** Scheduled, not estimated. */
  duration_minutes: number;
  /** Every scheduled call between the two, including ones realtime says are skipped. */
  stops_between: number;
}

export interface PlanResponse {
  from: StationRef;
  to: StationRef;
  at: IsoDateTime;
  fare: Fare | null;
  trips: PlanTrip[];
}

// --- /stations/{id}/departures ---------------------------------------------

export interface Departure extends TripBase {
  depart: PlatformTime;
  destination: StationRef;
}

export interface DeparturesResponse {
  station: StationRef;
  at: IsoDateTime;
  departures: Departure[];
}

// --- /vehicles --------------------------------------------------------------

export type VehicleStatus = 'incoming_at' | 'stopped_at' | 'in_transit_to' | null;

export interface Vehicle {
  vehicle_id: string;
  trip_id: string;
  /** null if the trip is not in the static feed. */
  short_name: string | null;
  route: RouteRef | null;
  headsign: string | null;
  lat: number;
  lon: number;
  /** Degrees clockwise from north; null when the feed omits it (511's Caltrain feed always does). */
  bearing: number | null;
  /** null when the feed omits it. */
  status: VehicleStatus;
  /** Platform id, as in trips[].stops[].stop_id; null when the feed omits it. */
  stop_id: string | null;
  timestamp: IsoDateTime;
}

// --- /trips/{id} ------------------------------------------------------------

export interface TripStop {
  sequence: number;
  stop_id: string;
  station_id: string;
  name: string;
  arrival: StopTime;
  departure: StopTime;
  skipped: boolean;
}

export interface TripDetail extends TripBase {
  bikes_allowed: boolean;
  wheelchair_accessible: boolean;
  stops: TripStop[];
  vehicle: Vehicle | null;
}

// --- /alerts ----------------------------------------------------------------

export interface ActivePeriod {
  start: IsoDateTime | null;
  end: IsoDateTime | null;
}

export interface Alert {
  id: string;
  header: string;
  description: string;
  /** "" when absent. */
  url: string;
  /** GTFS-realtime enum name, lowercased, e.g. technical_problem. */
  cause: string;
  /** GTFS-realtime enum name, lowercased, e.g. significant_delays. */
  effect: string;
  active_periods: ActivePeriod[];
  route_ids: string[];
  stop_ids: string[];
}
